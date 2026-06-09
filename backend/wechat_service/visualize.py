import json
import re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import networkx as nx

# ===== 中文字体配置 =====
_CHINESE_FONT_PROP = None
_CHINESE_FONT_NAMES = ["Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "FangSong"]

# 强制重建字体缓存（解决 matplotlib 缓存过期导致的找不到字体问题）
_font_dir = Path(matplotlib.get_cachedir())
for _cache_file in _font_dir.glob("fontlist-v*.json"):
    _cache_file.unlink(missing_ok=True)

fm._load_fontmanager(try_read_cache=False)

for _name in _CHINESE_FONT_NAMES:
    for _f in fm.fontManager.ttflist:
        if _f.name == _name:
            _CHINESE_FONT_PROP = fm.FontProperties(fname=_f.fname)
            break
    if _CHINESE_FONT_PROP:
        break

if _CHINESE_FONT_PROP:
    _FONT_NAME = _CHINESE_FONT_PROP.get_name()
    plt.rcParams["font.family"] = _FONT_NAME
    plt.rcParams["font.sans-serif"] = [_FONT_NAME] + plt.rcParams["font.sans-serif"]
else:
    _FONT_NAME = "sans-serif"
    plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False   # 解决负号显示问题


# 节点类型 → 颜色和形状映射
NODE_STYLE = {
    "检查": {"color": "#4A90D9", "shape": "o"},
    "分支": {"color": "#F5A623", "shape": "D"},
    "处理": {"color": "#F5A623", "shape": "o"},
    "结果": {"color": "#7ED321", "shape": "s"},
}

EDGE_STYLE = {
    "sequential":   {"style": "solid",  "color": "#333333"},
    "conditional":  {"style": "dashed", "color": "#999999"},
}


class VisualizeService:
    """将流程模板 JSON 渲染为有向流程图"""

    def render_template_graph(self, template_path: str | Path, output_path: str | None = None) -> str | list[str]:
        """
        从模板 JSON 文件渲染流程图。
        支持两种格式：
          - 单模板：{crime_type, nodes, edges}
          - 模板树：{keyword, sub_templates: [{label, template: {crime_type, nodes, edges}}]}
        template_path: 模板 JSON 文件路径
        output_path:   输出 PNG 路径（单模板）或目录（模板树），默认与模板同目录
        """
        template_path = Path(template_path)

        raw = template_path.read_text(encoding="utf-8")
        data = json.loads(raw)

        # 检测格式：模板树 vs 单模板
        sub_templates = data.get("sub_templates")
        if sub_templates:
            # 模板树格式：为每个子树渲染独立的图
            keyword = data.get("keyword", "流程")
            output_dir = Path(output_path) if output_path else template_path.parent / template_path.stem
            output_dir.mkdir(parents=True, exist_ok=True)
            results = []
            for i, st in enumerate(sub_templates):
                sub_data = st.get("template", {})
                sub_label = st.get("label", f"sub_{i}")
                safe_label = re.sub(r'[^\w\-]', '_', sub_label)
                sub_output = output_dir / f"{i+1}_{safe_label}.png"
                sub_data["crime_type"] = sub_data.get("crime_type", keyword)
                self._draw(sub_data, sub_output, subtitle=sub_label)
                results.append(str(sub_output))
                print(f"  图已保存: {sub_output}")
            return results
        else:
            # 单模板格式
            if output_path is None:
                output_path = template_path.with_suffix(".png")
            self._draw(data, output_path)
            print(f"  图已保存: {output_path}")
            return str(output_path)

    @staticmethod
    def _parse_template_json(raw: str) -> dict:
        """从 LLM 响应中提取 JSON（兼容 markdown 代码块包裹）"""
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
        return json.loads(raw)

    def _draw(self, data: dict, output_path: Path, subtitle: str = "") -> None:
        nodes_data = data.get("nodes", [])
        edges_data = data.get("edges", [])

        G = nx.DiGraph()
        node_labels = {}
        node_colors = []
        edge_styles = []

        for n in nodes_data:
            nid = n.get("id")
            label = n.get("label", str(nid))
            G.add_node(nid)
            node_labels[nid] = label
            style = NODE_STYLE.get(n.get("type", ""), NODE_STYLE["检查"])
            node_colors.append(style["color"])

        for e in edges_data:
            src = e.get("from") or e.get("source")
            tgt = e.get("to") or e.get("target")
            if src is not None and tgt is not None:
                G.add_edge(src, tgt)
                edge_style = EDGE_STYLE.get(e.get("type", "sequential"), EDGE_STYLE["sequential"])
                edge_styles.append(edge_style)

        # 拓扑分层布局（DAG 从上到下）
        try:
            layers = list(nx.topological_generations(G))
        except nx.NetworkXError:
            # 有环时退回力导向布局
            pos = nx.spring_layout(G, seed=42)
        else:
            pos = self._layer_layout(G, layers)

        plt.figure(figsize=(14, 10))
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1800, alpha=0.9)
        nx.draw_networkx_labels(G, pos, labels=node_labels, font_size=7,
                                font_family=_FONT_NAME)

        # 分别画顺序边和条件边
        seq_edges = [(u, v) for (u, v), s in zip(G.edges(), edge_styles) if s["style"] == "solid"]
        cond_edges = [(u, v) for (u, v), s in zip(G.edges(), edge_styles) if s["style"] == "dashed"]

        if seq_edges:
            nx.draw_networkx_edges(G, pos, edgelist=seq_edges, edge_color="#333333",
                                   arrows=True, arrowsize=15, width=1.5)
        if cond_edges:
            nx.draw_networkx_edges(G, pos, edgelist=cond_edges, edge_color="#999999",
                                   style="dashed", arrows=True, arrowsize=12, width=1)

        # 提取标题
        crime_type = data.get("crime_type", "流程模板")
        version = data.get("version", "")
        title = f"{crime_type} v{version}" if version else crime_type
        if subtitle:
            title = f"{title}\n[{subtitle}]"
        plt.title(title, fontsize=14)

        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

    @staticmethod
    def _layer_layout(G: nx.DiGraph, layers: list) -> dict:
        """按拓扑层级从上到下排列节点"""
        pos = {}
        for layer_idx, layer_nodes in enumerate(layers):
            n = len(layer_nodes)
            y = -layer_idx  # 层级越高越靠上
            for i, node in enumerate(layer_nodes):
                x = (i - (n - 1) / 2) * 1.5
                pos[node] = (x, y)
        return pos
