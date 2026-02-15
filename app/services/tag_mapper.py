"""Platform tag → internal Tag mapping.

Each OJ platform uses its own tag vocabulary (e.g. Luogu uses Chinese category
names like "动态规划").  The internal Tag table stores normalised English
identifiers like ``dp_linear``.  This module bridges the two with:

1. Static mapping dictionaries (fast, free, covers known tags)
2. Fallback to Tag.name / Tag.display_name exact match
3. Logging of unmatched tags so we can extend the dictionaries later
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.extensions import db
from app.models import Tag

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static mapping: platform tag text → list of internal Tag.name values
# One platform tag may map to multiple internal tags.
# ---------------------------------------------------------------------------

LUOGU_TAG_MAP: dict[str, list[str]] = {
    # Stage 1 – 语法基础
    "模拟": ["simulation"],
    "枚举": ["enumeration"],
    "排序": ["sort_basic", "sort_advanced"],
    "字符串": ["string_basic", "string_processing"],
    "循环": ["loop"],
    "数组": ["array"],
    "条件判断": ["condition"],
    "函数": ["function"],
    "结构体": ["struct"],
    "指针": ["pointer"],
    "文件读写": ["file_io"],
    "输入输出": ["io"],
    "变量": ["variables"],

    # Stage 2 – 基础算法
    "贪心": ["greedy_basic"],
    "二分": ["binary_search"],
    "二分答案": ["binary_search"],
    "前缀和": ["prefix_sum"],
    "差分": ["difference"],
    "双指针": ["two_pointer"],
    "尺取法": ["two_pointer"],
    "高精度": ["high_precision"],
    "递推": ["recursion"],
    "递归": ["recursion"],
    "位运算": ["bit_operation"],

    # Stage 3 – CSP-J
    "动态规划": ["dp_linear"],
    "线性DP": ["dp_linear"],
    "背包": ["dp_knapsack_basic"],
    "01背包": ["dp_knapsack_basic"],
    "完全背包": ["dp_knapsack_basic"],
    "搜索": ["dfs", "bfs"],
    "深搜": ["dfs"],
    "DFS": ["dfs"],
    "广搜": ["bfs"],
    "BFS": ["bfs"],
    "图论": ["graph_basic"],
    "数论": ["number_theory_basic"],
    "数学": ["number_theory_basic"],
    "素数": ["number_theory_basic"],
    "GCD": ["number_theory_basic"],
    "LCM": ["number_theory_basic"],
    "栈": ["stack"],
    "队列": ["queue"],
    "链表": ["linked_list"],
    "哈希": ["hash_table"],
    "散列": ["hash_table"],
    "滑动窗口": ["sliding_window"],
    "双端队列": ["deque"],
    "并查集": ["union_find"],
    "LIS": ["lis"],
    "最长上升子序列": ["lis"],

    # Stage 4 – CSP-S
    "区间DP": ["dp_interval"],
    "区间dp": ["dp_interval"],
    "树形DP": ["dp_tree"],
    "树形dp": ["dp_tree"],
    "状压DP": ["dp_bitmask"],
    "状压dp": ["dp_bitmask"],
    "数位DP": ["dp_digit"],
    "数位dp": ["dp_digit"],
    "剪枝": ["search_pruning"],
    "迭代加深": ["search_iterative_deepening"],
    "IDA*": ["search_iterative_deepening"],
    "双向BFS": ["search_bidirectional_bfs"],
    "双向搜索": ["search_bidirectional_bfs"],
    "A*": ["search_astar"],
    "启发式搜索": ["search_astar"],
    "最短路": ["shortest_path"],
    "Dijkstra": ["shortest_path"],
    "SPFA": ["shortest_path"],
    "Floyd": ["shortest_path"],
    "最小生成树": ["mst"],
    "Kruskal": ["mst"],
    "Prim": ["mst"],
    "拓扑排序": ["topo_sort"],
    "LCA": ["lca"],
    "最近公共祖先": ["lca"],
    "强连通分量": ["tarjan_scc"],
    "Tarjan": ["tarjan_scc"],
    "堆": ["heap"],
    "优先队列": ["heap"],
    "ST表": ["sparse_table"],
    "树状数组": ["bit"],
    "线段树": ["segment_tree"],
    "单调栈": ["monotone_stack"],
    "单调队列": ["monotone_queue"],
    "组合数学": ["combinatorics"],
    "排列组合": ["combinatorics"],
    "容斥原理": ["inclusion_exclusion"],
    "容斥": ["inclusion_exclusion"],
    "快速幂": ["fast_power"],
    "逆元": ["modular_inverse"],
    "KMP": ["kmp"],
    "字典树": ["trie"],
    "Trie": ["trie"],
    "字符串哈希": ["string_hash"],
    "折半搜索": ["meet_in_middle"],

    # Stage 5 – 省选
    "平衡树": ["balanced_tree"],
    "Treap": ["balanced_tree"],
    "Splay": ["balanced_tree"],
    "主席树": ["persistent_ds"],
    "可持久化": ["persistent_ds"],
    "树链剖分": ["heavy_light"],
    "点分治": ["centroid_decomposition"],
    "边分治": ["centroid_decomposition"],
    "后缀数组": ["suffix_array"],
    "后缀自动机": ["suffix_automaton"],
    "SAM": ["sam"],
    "AC自动机": ["ac_automaton"],
    "网络流": ["network_flow"],
    "最大流": ["network_flow"],
    "费用流": ["network_flow"],
    "最小割": ["network_flow"],
    "二分图匹配": ["bipartite_matching"],
    "匈牙利算法": ["bipartite_matching"],
    "二分图": ["bipartite_matching"],
    "概率DP": ["dp_probability"],
    "期望DP": ["dp_probability"],
    "博弈论": ["game_theory"],
    "SG函数": ["game_theory"],
    "CDQ分治": ["cdq_divide"],
    "整体二分": ["overall_binary"],
    "矩阵快速幂": ["matrix_power"],
    "矩阵乘法": ["matrix_power"],
    "高斯消元": ["gaussian_elimination"],
    "2-SAT": ["two_sat"],
    "斜率优化": ["slope_optimization"],

    # Stage 6 – NOI
    "FFT": ["fft_ntt"],
    "NTT": ["fft_ntt"],
    "多项式": ["fft_ntt"],
    "虚树": ["virtual_tree"],
    "回文自动机": ["palindrome_automaton"],
    "LCT": ["lct"],
    "Link-Cut Tree": ["lct"],
    "插头DP": ["dp_plug"],
    "仙人掌": ["cactus_graph"],
    "杜教筛": ["du_sieve"],
    "Min-25筛": ["min25_sieve"],
    "计算几何": ["computational_geometry"],
}

BBCOJ_TAG_MAP: dict[str, list[str]] = {
    # HOJ systems typically use Chinese tag names similar to Luogu
    "模拟": ["simulation"],
    "枚举": ["enumeration"],
    "排序": ["sort_basic", "sort_advanced"],
    "字符串": ["string_basic", "string_processing"],
    "循环": ["loop"],
    "数组": ["array"],
    "贪心": ["greedy_basic"],
    "二分": ["binary_search"],
    "二分查找": ["binary_search"],
    "前缀和": ["prefix_sum"],
    "差分": ["difference"],
    "双指针": ["two_pointer"],
    "高精度": ["high_precision"],
    "递推": ["recursion"],
    "递归": ["recursion"],
    "位运算": ["bit_operation"],
    "动态规划": ["dp_linear"],
    "DP": ["dp_linear"],
    "dp": ["dp_linear"],
    "线性DP": ["dp_linear"],
    "背包": ["dp_knapsack_basic"],
    "01背包": ["dp_knapsack_basic"],
    "完全背包": ["dp_knapsack_basic"],
    "搜索": ["dfs", "bfs"],
    "深搜": ["dfs"],
    "DFS": ["dfs"],
    "广搜": ["bfs"],
    "BFS": ["bfs"],
    "图论": ["graph_basic"],
    "数论": ["number_theory_basic"],
    "数学": ["number_theory_basic"],
    "栈": ["stack"],
    "队列": ["queue"],
    "链表": ["linked_list"],
    "哈希": ["hash_table"],
    "并查集": ["union_find"],
    "区间DP": ["dp_interval"],
    "树形DP": ["dp_tree"],
    "状压DP": ["dp_bitmask"],
    "数位DP": ["dp_digit"],
    "剪枝": ["search_pruning"],
    "最短路": ["shortest_path"],
    "Dijkstra": ["shortest_path"],
    "SPFA": ["shortest_path"],
    "Floyd": ["shortest_path"],
    "最小生成树": ["mst"],
    "拓扑排序": ["topo_sort"],
    "LCA": ["lca"],
    "Tarjan": ["tarjan_scc"],
    "强连通分量": ["tarjan_scc"],
    "堆": ["heap"],
    "优先队列": ["heap"],
    "树状数组": ["bit"],
    "线段树": ["segment_tree"],
    "单调栈": ["monotone_stack"],
    "单调队列": ["monotone_queue"],
    "组合数学": ["combinatorics"],
    "快速幂": ["fast_power"],
    "KMP": ["kmp"],
    "字典树": ["trie"],
    "Trie": ["trie"],
    "网络流": ["network_flow"],
    "二分图": ["bipartite_matching"],
    "博弈论": ["game_theory"],
}

YBT_TAG_MAP: dict[str, list[str]] = {
    # 一本通 currently returns empty tags
}

_PLATFORM_MAPS: dict[str, dict[str, list[str]]] = {
    "luogu": LUOGU_TAG_MAP,
    "bbcoj": BBCOJ_TAG_MAP,
    "ybt": YBT_TAG_MAP,
}


class TagMapper:
    """Map platform-specific tag names to internal Tag objects.

    Matching strategy (in priority order):
    1. Static mapping dictionary for the platform
    2. Tag.name exact match
    3. Tag.display_name exact match
    Unmatched tags are logged for future dictionary updates.
    """

    def __init__(self, platform: str):
        self.platform = platform
        self._static_map = _PLATFORM_MAPS.get(platform, {})
        # Cache Tag objects by name within a session to avoid repeated queries
        self._tag_cache: dict[str, Tag | None] = {}

    def _get_tag(self, internal_name: str) -> Tag | None:
        """Retrieve an internal Tag by name, with caching."""
        if internal_name not in self._tag_cache:
            tag = Tag.query.filter_by(name=internal_name).first()
            self._tag_cache[internal_name] = tag
        return self._tag_cache[internal_name]

    def _get_tag_by_display_name(self, display_name: str) -> Tag | None:
        """Retrieve an internal Tag by display_name, with caching."""
        cache_key = f"__display__{display_name}"
        if cache_key not in self._tag_cache:
            tag = Tag.query.filter_by(display_name=display_name).first()
            self._tag_cache[cache_key] = tag
        return self._tag_cache[cache_key]

    def map_tags(self, platform_tags: list[str]) -> list[Tag]:
        """Map a list of platform tag strings to internal Tag objects.

        Returns a deduplicated list of Tag instances (order preserved).
        """
        seen_ids: set[int] = set()
        result: list[Tag] = []

        for pt in platform_tags:
            pt = pt.strip()
            if not pt:
                continue

            mapped = False

            # Strategy 1: static mapping dictionary
            internal_names = self._static_map.get(pt)
            if internal_names:
                for name in internal_names:
                    tag = self._get_tag(name)
                    if tag and tag.id not in seen_ids:
                        seen_ids.add(tag.id)
                        result.append(tag)
                        mapped = True

            if mapped:
                continue

            # Strategy 2: exact match on Tag.name
            tag = self._get_tag(pt)
            if tag and tag.id not in seen_ids:
                seen_ids.add(tag.id)
                result.append(tag)
                continue

            # Strategy 3: exact match on Tag.display_name
            tag = self._get_tag_by_display_name(pt)
            if tag and tag.id not in seen_ids:
                seen_ids.add(tag.id)
                result.append(tag)
                continue

            # Unmatched – log for future dictionary updates
            logger.warning(
                "Unmapped tag on %s: %r — consider adding to %s_TAG_MAP",
                self.platform, pt, self.platform.upper(),
            )

        return result
