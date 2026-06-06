package main

/*
#cgo CFLAGS: -x c
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define MIN_HEX_PATTERN_LEN 64
#define MAX_HEX_PATTERN_LEN 192
#define CHUNK_SIZE (2 * 1024 * 1024)
#define MAX_REGION_SIZE (50ULL * 1024ULL * 1024ULL)
#define MAX_MATCHES 8192

static int is_hex_char(unsigned char c) {
	return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

static void lower_hex(char* s, int n) {
	for (int i = 0; i < n; i++) {
		if (s[i] >= 'A' && s[i] <= 'F') s[i] += 32;
	}
}

static int scan_key_salt_pairs(int pid, char* out_buf, int out_cap, int* out_regions) {
	if (out_buf == NULL || out_cap <= 0) return -1;
	out_buf[0] = '\0';
	if (out_regions) *out_regions = 0;

	mach_port_t task = MACH_PORT_NULL;
	kern_return_t kr = task_for_pid(mach_task_self(), (pid_t)pid, &task);
	if (kr != KERN_SUCCESS || task == MACH_PORT_NULL) return -2;

	char seen[MAX_MATCHES][98];
	int seen_count = 0;
	int out_len = 0;
	mach_vm_address_t addr = 0;

	for (;;) {
		mach_vm_size_t size = 0;
		vm_region_basic_info_data_64_t info;
		mach_msg_type_number_t info_count = VM_REGION_BASIC_INFO_COUNT_64;
		mach_port_t object_name = MACH_PORT_NULL;

		kr = mach_vm_region(task, &addr, &size, VM_REGION_BASIC_INFO_64,
		                    (vm_region_info_t)&info, &info_count, &object_name);
		if (kr != KERN_SUCCESS) break;
		if (size == 0) {
			addr++;
			continue;
		}
		if (out_regions) *out_regions += 1;

		if (size <= MAX_REGION_SIZE &&
		    (info.protection & (VM_PROT_READ | VM_PROT_WRITE)) == (VM_PROT_READ | VM_PROT_WRITE)) {
			mach_vm_address_t cur = addr;
			mach_vm_address_t end = addr + size;

			while (cur < end) {
				mach_vm_size_t chunk = end - cur;
				if (chunk > CHUNK_SIZE) chunk = CHUNK_SIZE;

				vm_offset_t data = 0;
				mach_msg_type_number_t data_count = 0;
				kr = mach_vm_read(task, cur, chunk, &data, &data_count);
				if (kr == KERN_SUCCESS && data != 0 && data_count > MIN_HEX_PATTERN_LEN + 3) {
					unsigned char* buf = (unsigned char*)data;
					for (mach_msg_type_number_t i = 0; i + MIN_HEX_PATTERN_LEN + 3 < data_count; i++) {
						if (buf[i] != 'x' || buf[i+1] != '\'') continue;
						int hex_len = 0;
						while (hex_len < MAX_HEX_PATTERN_LEN &&
						       i + 2 + hex_len < data_count &&
						       is_hex_char(buf[i+2+hex_len])) {
							hex_len++;
						}
						if (hex_len < MIN_HEX_PATTERN_LEN ||
						    hex_len % 2 != 0 ||
						    i + 2 + hex_len >= data_count ||
						    buf[i+2+hex_len] != '\'') continue;
						if (hex_len != 64 && hex_len < 96) continue;

						char key_hex[65];
						char salt_hex[33];
						memcpy(key_hex, buf+i+2, 64);
						key_hex[64] = '\0';
						if (hex_len >= 96) {
							memcpy(salt_hex, buf+i+2+hex_len-32, 32);
							salt_hex[32] = '\0';
						} else {
							salt_hex[0] = '\0';
						}
						lower_hex(key_hex, 64);
						if (salt_hex[0] != '\0') lower_hex(salt_hex, 32);

						char uniq[98];
						memset(uniq, 0, sizeof(uniq));
						memcpy(uniq, key_hex, 64);
						uniq[64] = ',';
						if (salt_hex[0] != '\0') memcpy(uniq+65, salt_hex, 32);
						int dup = 0;
						for (int k = 0; k < seen_count; k++) {
							if (strcmp(seen[k], uniq) == 0) {
								dup = 1;
								break;
							}
						}
						if (dup) continue;
						if (seen_count < MAX_MATCHES) {
							memcpy(seen[seen_count], uniq, 98);
							seen_count++;
						}

						int salt_len = salt_hex[0] == '\0' ? 0 : 32;
						int need = 64 + 1 + salt_len + 1;
						if (out_len + need + 1 >= out_cap) {
							mach_vm_deallocate(mach_task_self(), data, data_count);
							return seen_count;
						}
						memcpy(out_buf+out_len, key_hex, 64);
						out_len += 64;
						out_buf[out_len++] = ',';
						if (salt_len > 0) {
							memcpy(out_buf+out_len, salt_hex, 32);
							out_len += 32;
						}
						out_buf[out_len++] = '\n';
						out_buf[out_len] = '\0';
					}
					mach_vm_deallocate(mach_task_self(), data, data_count);
				}
				if (chunk > MAX_HEX_PATTERN_LEN + 3) {
					cur += chunk - (MAX_HEX_PATTERN_LEN + 3);
				} else {
					cur += chunk;
				}
			}
		}
		addr += size;
	}
	return seen_count;
}
*/
import "C"

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha512"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

const (
	pageSize = 4096
	keySize  = 32
	saltSize = 16
)

type dbInfo struct {
	rel   string
	salt  string
	page1 []byte
}

type keyEntry struct {
	EncKey string `json:"enc_key"`
}

type pair struct {
	key  string
	salt string
}

func main() {
	pid := flag.Int("pid", 0, "WeChat process PID")
	dataDir := flag.String("data-dir", "", "WeChat account data directory")
	flag.Parse()
	if *pid <= 0 || strings.TrimSpace(*dataDir) == "" {
		fmt.Fprintln(os.Stderr, "usage: macscan-min --pid <pid> --data-dir <account-dir>")
		os.Exit(2)
	}

	dbs, err := collectDBs(*dataDir)
	if err != nil {
		fmt.Fprintln(os.Stderr, "collect failed:", err)
		os.Exit(1)
	}
	saltToDBs := map[string][]dbInfo{}
	for _, db := range dbs {
		saltToDBs[db.salt] = append(saltToDBs[db.salt], db)
	}
	fmt.Fprintf(os.Stderr, "dbs=%d salts=%d\n", len(dbs), len(saltToDBs))

	outCap := 2 * 1024 * 1024
	out := C.malloc(C.size_t(outCap))
	if out == nil {
		fmt.Fprintln(os.Stderr, "malloc failed")
		os.Exit(1)
	}
	defer C.free(out)

	var regions C.int
	n := C.scan_key_salt_pairs(C.int(*pid), (*C.char)(out), C.int(outCap), &regions)
	if n < 0 {
		fmt.Fprintf(os.Stderr, "scan failed code=%d regions=%d\n", int(n), int(regions))
		os.Exit(1)
	}
	pairs := parsePairs(C.GoString((*C.char)(out)))
	fmt.Fprintf(os.Stderr, "regions=%d pairs=%d\n", int(regions), len(pairs))

	keySet := map[string]struct{}{}
	for _, pair := range pairs {
		keySet[pair.key] = struct{}{}
	}

	result := map[string]keyEntry{}
	for keyHex := range keySet {
		keyBytes, err := hex.DecodeString(keyHex)
		if err != nil || len(keyBytes) != keySize {
			continue
		}
		for _, db := range dbs {
			if verifyKey(keyBytes, db.page1) {
				result[db.rel] = keyEntry{EncKey: keyHex}
			}
		}
	}
	if len(result) == 0 {
		fmt.Fprintln(os.Stderr, "no matching keys")
		os.Exit(1)
	}

	path := filepath.Join(filepath.Clean(*dataDir), "all_keys.json")
	encoded, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "marshal failed:", err)
		os.Exit(1)
	}
	if err := os.WriteFile(path, encoded, 0600); err != nil {
		fmt.Fprintln(os.Stderr, "write failed:", err)
		os.Exit(1)
	}
	if uid, gid, ok := ownerOf(filepath.Clean(*dataDir)); ok {
		_ = os.Chown(path, uid, gid)
		_ = os.Chmod(path, 0600)
	}
	fmt.Fprintf(os.Stderr, "keys_written=%d path=%s\n", len(result), path)
	fmt.Println("ok")
}

func parsePairs(raw string) []pair {
	lines := strings.Split(raw, "\n")
	out := make([]pair, 0, len(lines))
	for _, line := range lines {
		parts := strings.Split(strings.TrimSpace(line), ",")
		if len(parts) != 2 || len(parts[0]) != 64 {
			continue
		}
		if len(parts[1]) != 0 && len(parts[1]) != 32 {
			continue
		}
		out = append(out, pair{key: parts[0], salt: parts[1]})
	}
	return out
}

func collectDBs(dataDir string) ([]dbInfo, error) {
	dbStorage := filepath.Join(filepath.Clean(dataDir), "db_storage")
	var out []dbInfo
	err := filepath.WalkDir(dbStorage, func(path string, d os.DirEntry, walkErr error) error {
		if walkErr != nil || d.IsDir() {
			return nil
		}
		if !strings.HasSuffix(strings.ToLower(path), ".db") {
			return nil
		}
		f, err := os.Open(path)
		if err != nil {
			return nil
		}
		defer f.Close()
		page1 := make([]byte, pageSize)
		if _, err := io.ReadFull(f, page1); err != nil {
			return nil
		}
		if bytes.HasPrefix(page1, []byte("SQLite format 3")) {
			return nil
		}
		rel, err := filepath.Rel(dbStorage, path)
		if err != nil {
			return nil
		}
		out = append(out, dbInfo{
			rel:   filepath.ToSlash(rel),
			salt:  hex.EncodeToString(page1[:saltSize]),
			page1: page1,
		})
		return nil
	})
	return out, err
}

func verifyKey(key, page1 []byte) bool {
	if len(key) != keySize || len(page1) < pageSize {
		return false
	}
	salt := page1[:saltSize]
	macSalt := make([]byte, saltSize)
	for i, b := range salt {
		macSalt[i] = b ^ 0x3a
	}
	macKey := pbkdf2HMACSHA512(key, macSalt, 2, keySize)
	h := hmac.New(sha512.New, macKey)
	h.Write(page1[saltSize : pageSize-80+16])
	var pg [4]byte
	binary.LittleEndian.PutUint32(pg[:], 1)
	h.Write(pg[:])
	return hmac.Equal(h.Sum(nil), page1[pageSize-64:pageSize])
}

func pbkdf2HMACSHA512(password, salt []byte, iter, keyLen int) []byte {
	var dk []byte
	block := uint32(1)
	for len(dk) < keyLen {
		u := pbkdf2U(password, salt, block)
		t := append([]byte(nil), u...)
		for i := 1; i < iter; i++ {
			u = pbkdf2PRF(password, u)
			for j := range t {
				t[j] ^= u[j]
			}
		}
		dk = append(dk, t...)
		block++
	}
	return dk[:keyLen]
}

func pbkdf2U(password, salt []byte, block uint32) []byte {
	msg := make([]byte, len(salt)+4)
	copy(msg, salt)
	binary.BigEndian.PutUint32(msg[len(salt):], block)
	return pbkdf2PRF(password, msg)
}

func pbkdf2PRF(password, data []byte) []byte {
	h := hmac.New(sha512.New, password)
	h.Write(data)
	return h.Sum(nil)
}

func ownerOf(path string) (int, int, bool) {
	st, err := os.Stat(path)
	if err != nil {
		return 0, 0, false
	}
	raw, ok := st.Sys().(*syscall.Stat_t)
	if !ok {
		return 0, 0, false
	}
	return int(raw.Uid), int(raw.Gid), true
}
