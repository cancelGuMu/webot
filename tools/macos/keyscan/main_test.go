package main

import "testing"

func TestParsePairsAcceptsSaltedAndKeyOnly(t *testing.T) {
	key := "a123456789abcdefa123456789abcdefa123456789abcdefa123456789abcdef"
	salt := "b123456789abcdefb123456789abcdef"
	raw := key + "," + salt + "\n" + key + ",\n"

	pairs := parsePairs(raw)

	if len(pairs) != 2 {
		t.Fatalf("len(pairs) = %d, want 2", len(pairs))
	}
	if pairs[0].key != key || pairs[0].salt != salt {
		t.Fatalf("salted pair = %+v", pairs[0])
	}
	if pairs[1].key != key || pairs[1].salt != "" {
		t.Fatalf("key-only pair = %+v", pairs[1])
	}
}

func TestParsePairsRejectsMalformedLines(t *testing.T) {
	key := "a123456789abcdefa123456789abcdefa123456789abcdefa123456789abcdef"
	raw := "bad,\n" +
		key + ",short\n" +
		key[:63] + ",\n"

	pairs := parsePairs(raw)

	if len(pairs) != 0 {
		t.Fatalf("len(pairs) = %d, want 0", len(pairs))
	}
}
