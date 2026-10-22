# 水利工程基础信息一张图 · 工程说明（shuili）

- 包名：`com.shuili.yitu`　版本：`4.02`（code 102）　数据量：557
- 独立 Git 仓库：`shuili-yitu`（main 分支）
- 百度网盘子目录：`水利一张图`

## 目录

```
webroot/        应用源码（编辑边界）
native-shell/   原生壳源码（Win/UOS[/iOS]）
build/          构建脚本
docs/           文档
version.json   版本信息
```

## 快速开始

```bash
cd D:/Users/WorkBuddy/shuili
# 浏览器直接打开 webroot/index.html 即可运行（需本地静态服务或 WebView2/UOS 壳）
```

## 构建四端
详见 [BUILD.md](BUILD.md)。原生壳映射：

- win-water-webview2（标题：水利工程基础信息一张图）
- uos-water-pyqt6
- water-ios

## 已知特性

- 类型图形图标升级后，地图标记须按类型显示专属图形（闸/泵/渠/桥智能匹配），图例同步图标化。
- AI 子菜单默认隐藏、可一键显示/隐藏（见近20天经验：公开版策略 AI 可用 + 组织脱敏拟真）。
- 运行维护菜单含备忘录功能；设置菜单含软件升级/数据导出/导入。

> 隔离规范与经验教训见顶层 `D:/Users/WorkBuddy/三项目总览与隔离规范.md`。