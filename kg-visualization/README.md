# 心血管疾病预防知识图谱

使用三份已验收的 RAGFlow JSON，在浏览器中逐层探索实体、关系和文献证据。应用使用本地静态数据，可独立运行。

## 启动

需要 Node.js 20.19+（若使用 Node.js 22，则需 22.12+）、pnpm 和 Python 3.9+。在项目目录运行：

```powershell
cd kg-visualization
pnpm install --frozen-lockfile
python scripts/build_graph_data.py
pnpm dev
```

打开 [http://127.0.0.1:5187/](http://127.0.0.1:5187/)。项目已附带生成的数据文件，直接启动时也可以使用现有数据。端口被占用时，使用 `pnpm dev --port 5188`。

依赖锁定版本为 Vue 3.5.46、TypeScript 5.9.3、Vite 7.3.8、AntV G6 5.1.1 和 pnpm 12.3.4。Python 脚本仅使用标准库。G6 实现参考 [数据 API](https://g6.antv.antgroup.com/en/api/data)、[事件 API](https://g6.antv.antgroup.com/en/api/event) 和 [Force 布局](https://g6.antv.antgroup.com/en/manual/layout/ForceLayout/)。

## 数据来源

数据路径相对前端目录，来源见[仓库 README](../README.md)。

| 文献 | 正式 JSON 路径 | 实体 | 关系 | 证据 |
| --- | --- | ---: | ---: | ---: |
| D1 中国心血管病一级预防指南 | `../output/primary-prevention-triples/triples.json` | 53 | 59 | 37 |
| D2 中国心血管健康与疾病报告 2024 | `../output/cardiovascular-report-2024-triples/triples.json` | 107 | 140 | 99 |
| D3 中国健康生活方式预防心血管代谢疾病指南 | `../output/healthy-lifestyle-triples/triples.json` | 20 | 19 | 15 |
| 合并前 | | 180 | 218 | 151 |
| 合并后 | | 159 | 215 | 151 |

原始实体和关系类型已使用中文，三类原始 ID 均使用文献前缀，未发现跨文献 ID 冲突。图谱覆盖危险因素、心血管疾病、健康指标和人群，关系包括增加风险、相关和导致。

## 转换与更新

- 读取 `metadata`、`entities`、`relations` 和 `evidence`。源文件的 `triples` 是相同关系的详细视图，正式关系数组已提供要用的数据。
- 实体名称做 Unicode NFKC 规范化并归并空白。按规范名称和中文类型精确去重，保留别名供搜索。
- 边按全局起点、终点、中文关系类型和方向标记合并。保留 `source`、`target` 与 `directed`。画布对有向关系绘制箭头，对无向关系绘制虚线。
- 通过文献 ID 与原始 ID 追溯每条实体和关系。证据使用文献命名空间保留原始页码、引文及证据 ID。关系记录还保留与证据对应的适用条件。
- 缺少页码或引文时使用 `null`。异常记录及不可引用的端点或证据都会计入报告。同篇文献内的重复 ID 会中止构建，因为无法确定引用目标。
- 更新原始导出后重新运行 `python scripts/build_graph_data.py`，然后刷新页面。路径变化时可按 D1、D2、D3 顺序传入三个绝对路径。脚本写入 `public/data/graph-data.json` 与 `public/data/build-report.json`，原始导出仅供读取。

## 交互

默认以冠心病为中心，推荐入口按关联关系数量排列。点击画布节点展开直接关联，继续点击新节点探索下一层。右侧面板支持展开、收起、查看直接关联和打开文献证据。搜索匹配实体名称与别名，选中结果后以该实体重新开始。重置按钮恢复默认中心及筛选条件。

实体与关系筛选也作用于展开结果，探索中心始终可见。画布支持拖动节点、拖动画布、鼠标滚轮缩放和适配画布。G6 Force 布局从父节点周围排布新增节点，并通过增加已显示节点的布局质量抑制其位移。

全图概览保留当前筛选条件，切回探索时恢复逐层展开状态。概览在关系较多时按需显示边标签，悬停和选中均可查看。若筛选后仍超过 600 个节点或 1400 条边，页面会提示缩小概览范围。

## 目录

| 路径 | 职责 |
| --- | --- |
| `public/data/` | 统一图谱及构建校验报告 |
| `scripts/build_graph_data.py` | 原始 JSON 合并、追溯字段和校验 |
| `src/components/` | 画布、筛选栏、图例、详情与证据 |
| `src/composables/useKnowledgeGraph.ts` | 数据加载和探索状态 |
| `src/utils/` | 筛选、搜索、遍历与 G6 表示 |
| `src/types/graph.ts` | 图谱和证据类型 |
| `tests/` | Python 数据校验、Vitest 单元测试及 Edge 交互测试 |

## 测试和构建

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
pnpm test
pnpm test:browser
pnpm build
```

浏览器测试默认使用本机 Microsoft Edge，另开 4187 端口。可通过环境变量 `PLAYWRIGHT_CHANNEL` 选择已安装的其他 Playwright 浏览器渠道。`pnpm build` 产物位于 `dist/`，使用静态 HTTP 服务托管即可。

## 集成到现有 Vue 平台

可将 `App.vue` 的探索页作为独立路由，迁入组件、组合式函数、工具、类型和样式，给画布父容器提供可计算高度。把 `useKnowledgeGraph.ts` 中的数据获取地址改为平台静态资源地址或未来的 FastAPI 接口，并维持 `KnowledgeGraph` 响应结构。图谱转换、交互和证据展示可继续复用。
