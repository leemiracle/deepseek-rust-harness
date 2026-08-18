# [kext4] panic 通道密度偏高（xattr.rs 46 处 / superblock.rs 464 处），是否需要策略声明？

## 现象（静态统计，非 diff 增量）

对 `fs/filesystems/kext4/` 做 panic 通道统计（`unwrap()/panic!/todo!/unimplemented!/unreachable!`）：

| 文件 | 静态计数 | 备注 |
|---|---|---|
| `src/superblock.rs` | 464 | 含 exhaustive match 的 `unreachable!` 惯用法（合理占比未知） |
| `src/xattr.rs` | 46 | !624 xattr 迁移 PR 的 diff 新增行中即含 27 处 |
| `src/disk/superblock.rs` | 14 | |

```bash
grep -cE '\.unwrap\(\)|panic!|todo!|unimplemented!|unreachable!' fs/filesystems/kext4/src/{xattr,superblock,disk/superblock}.rs
```

## 为什么想提出来讨论

no_std 内核语境下 panic = 系统崩溃（无 unwind、无进程隔离兜底）。这不是"必须改错"的 report，而是策略问题：

1. kext4 对**磁盘数据（on-disk metadata）解析路径**的 panic 容忍度是什么？损坏镜像触发 `unwrap` 导致整个内核 panic，是否符合设计意图？
2. exhaustive match 的 `unreachable!` 与"信任自己写死的枚举"是否值得区分统计？
3. 是否适合在 kext4 模块级声明 panic 策略（哪些路径允许、哪些必须 `Result` 传播），作为后续贡献者的对照基线？

## 顺带：无理由的 lint 豁免

`src/xattr.rs` 有三处 `#[allow(clippy::too_many_arguments)]`（L1152/L1227/L1267）无注释说明豁免理由。单点豁免本身可接受，但按惯例建议附 `// reason` 一行，方便 review 与后续清理（参数打包成 struct 往往也是 API 改进信号）。

## 环境说明

自动化验证环境（agent-driven harness）对 main 分支的静态扫描；!624 diff 级数据来自 graph 守卫对 `HEAD~1` 的结构分析。
