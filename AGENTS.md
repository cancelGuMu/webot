# AGENTS.md

## 每次修改必须提交 Git 到本地

每次对代码的修改完成后，必须执行 `git add` 和 `git commit`，写清楚改动内容和原因。**只提交到本地仓库，不 push 到 GitHub。**

```bash
git add -A
git commit -m "<描述做了什么，为什么>"
```

## 每次修改必须重新打包

每次修改完成后，必须重新执行 PyInstaller 打包，生成最新的 `dist/webot.exe`。

```bash
# 如果修改了前端代码，先构建前端
cd ui && npm run build && cd ..
# 打包
pyinstaller build.spec
```
