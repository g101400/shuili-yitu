# 水利工程基础信息一张图 · 构建手册（shuili）

> 构建脚本继承自单体仓库 `gujian4060`，**所有绝对路径须重指为本工程根 `D:/Users/WorkBuddy/shuili`**。

## 原生壳映射

- win-water-webview2（标题：水利工程基础信息一张图）
- uos-water-pyqt6
- water-ios

## 各端构建

### Android（APK）
- 入口：`build/targets/android/build_apk.sh`；`build/targets/android/app/src/main/java/com/...` 包名须改为 `com.shuili.yitu`。
### Windows（exe/msi）
- 壳：`native-shell/win-<x>/Program.cs` + `build_msi.wxs`；壳以 `AppContext.BaseDirectory/webroot` 承载网页，标题见上表。
### 统信 UOS（deb，x86_64/arm64/mips64el）
- 壳：`native-shell/uos-<x>/main.py` + `build_deb.sh`；以 `WEBROOT=<壳目录>/webroot` 承载。
### iOS（PWA 可托管包）
- 脚本：`native-shell/water-ios/build_ios_zip.py`、`make_secure_internal_pwa.py`（历史发布包在 `apple-package/` 已不入库）。

## 关键规则（防互相影响 / 防假绿）
1. 每个工程只构建自己的 `webroot/`，绝不引用兄弟工程目录。
2. 构建脚本路径用 `PROJECT_ROOT` 锚定，禁止 CWD 相对路径。
3. 出包前清同版本旧包，避免 `_bak_*`/`webroot_bak_*` 夹带污染（曾把安装包撑大 50 倍）。
4. 门禁断言计数必须 >0 且等于登记下限，零覆盖'全部通过'是假绿。