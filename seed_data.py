"""Seed data script for knowledge point tags.
Run with: python seed_data.py
"""
import os
import sys
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import Tag

TAGS = [
    # Stage 1: 语法基础
    {"name": "variables", "display_name": "变量与数据类型", "category": "basic", "stage": 1},
    {"name": "io", "display_name": "输入输出", "category": "basic", "stage": 1},
    {"name": "condition", "display_name": "条件判断", "category": "basic", "stage": 1},
    {"name": "loop", "display_name": "循环", "category": "basic", "stage": 1},
    {"name": "array", "display_name": "数组", "category": "basic", "stage": 1},
    {"name": "function", "display_name": "函数", "category": "basic", "stage": 1},
    {"name": "string_basic", "display_name": "字符串处理", "category": "string", "stage": 1},
    {"name": "struct", "display_name": "结构体", "category": "basic", "stage": 1},
    {"name": "pointer", "display_name": "指针/引用", "category": "basic", "stage": 1},
    {"name": "file_io", "display_name": "文件读写", "category": "basic", "stage": 1},

    # Stage 2: 基础算法
    {"name": "simulation", "display_name": "模拟", "category": "basic", "stage": 2},
    {"name": "enumeration", "display_name": "枚举", "category": "basic", "stage": 2},
    {"name": "sort_basic", "display_name": "排序(冒泡/选择/插入)", "category": "basic", "stage": 2, "prerequisite_tags": '["array", "loop"]'},
    {"name": "sort_advanced", "display_name": "排序(快排/归并)", "category": "basic", "stage": 2, "prerequisite_tags": '["sort_basic", "function"]'},
    {"name": "binary_search", "display_name": "二分查找", "category": "basic", "stage": 2, "prerequisite_tags": '["sort_basic"]'},
    {"name": "prefix_sum", "display_name": "前缀和", "category": "basic", "stage": 2, "prerequisite_tags": '["array"]'},
    {"name": "difference", "display_name": "差分", "category": "basic", "stage": 2, "prerequisite_tags": '["prefix_sum"]'},
    {"name": "two_pointer", "display_name": "双指针", "category": "basic", "stage": 2, "prerequisite_tags": '["array", "sort_basic"]'},
    {"name": "greedy_basic", "display_name": "贪心", "category": "basic", "stage": 2, "prerequisite_tags": '["sort_basic"]'},
    {"name": "high_precision", "display_name": "高精度计算", "category": "math", "stage": 2, "prerequisite_tags": '["array", "string_basic"]'},
    {"name": "recursion", "display_name": "递推与递归", "category": "basic", "stage": 2, "prerequisite_tags": '["function"]'},

    # Stage 3: CSP-J
    {"name": "stack", "display_name": "栈", "category": "ds", "stage": 3, "prerequisite_tags": '["array"]'},
    {"name": "queue", "display_name": "队列", "category": "ds", "stage": 3, "prerequisite_tags": '["array"]'},
    {"name": "linked_list", "display_name": "链表", "category": "ds", "stage": 3, "prerequisite_tags": '["pointer", "struct"]'},
    {"name": "dfs", "display_name": "DFS深度优先搜索", "category": "search", "stage": 3, "prerequisite_tags": '["recursion"]'},
    {"name": "bfs", "display_name": "BFS广度优先搜索", "category": "search", "stage": 3, "prerequisite_tags": '["queue"]'},
    {"name": "dp_linear", "display_name": "线性DP", "category": "dp", "stage": 3, "prerequisite_tags": '["recursion", "array"]'},
    {"name": "dp_knapsack_basic", "display_name": "简单背包", "category": "dp", "stage": 3, "prerequisite_tags": '["dp_linear"]'},
    {"name": "number_theory_basic", "display_name": "基础数论(GCD/LCM/素数筛)", "category": "math", "stage": 3, "prerequisite_tags": '["loop", "function"]'},
    {"name": "graph_basic", "display_name": "简单图论(邻接表/矩阵/遍历)", "category": "graph", "stage": 3, "prerequisite_tags": '["dfs", "bfs", "array"]'},
    {"name": "string_processing", "display_name": "基础字符串处理", "category": "string", "stage": 3, "prerequisite_tags": '["string_basic", "array"]'},

    # Stage 4: CSP-S
    {"name": "dp_interval", "display_name": "区间DP", "category": "dp", "stage": 4, "prerequisite_tags": '["dp_linear"]'},
    {"name": "dp_tree", "display_name": "树形DP", "category": "dp", "stage": 4, "prerequisite_tags": '["dp_linear", "dfs", "graph_basic"]'},
    {"name": "dp_bitmask", "display_name": "状压DP", "category": "dp", "stage": 4, "prerequisite_tags": '["dp_linear"]'},
    {"name": "dp_digit", "display_name": "数位DP", "category": "dp", "stage": 4, "prerequisite_tags": '["dp_linear", "recursion"]'},
    {"name": "search_pruning", "display_name": "搜索剪枝", "category": "search", "stage": 4, "prerequisite_tags": '["dfs", "bfs"]'},
    {"name": "search_iterative_deepening", "display_name": "迭代加深", "category": "search", "stage": 4, "prerequisite_tags": '["dfs"]'},
    {"name": "search_bidirectional_bfs", "display_name": "双向BFS", "category": "search", "stage": 4, "prerequisite_tags": '["bfs"]'},
    {"name": "search_astar", "display_name": "A*搜索", "category": "search", "stage": 4, "prerequisite_tags": '["bfs"]'},
    {"name": "shortest_path", "display_name": "最短路(Dijkstra/SPFA/Floyd)", "category": "graph", "stage": 4, "prerequisite_tags": '["graph_basic"]'},
    {"name": "mst", "display_name": "最小生成树(Kruskal/Prim)", "category": "graph", "stage": 4, "prerequisite_tags": '["graph_basic", "union_find"]'},
    {"name": "topo_sort", "display_name": "拓扑排序", "category": "graph", "stage": 4, "prerequisite_tags": '["graph_basic", "queue"]'},
    {"name": "lca", "display_name": "LCA最近公共祖先", "category": "graph", "stage": 4, "prerequisite_tags": '["graph_basic", "dfs"]'},
    {"name": "tarjan_scc", "display_name": "强连通分量(Tarjan)", "category": "graph", "stage": 4, "prerequisite_tags": '["dfs", "graph_basic"]'},
    {"name": "union_find", "display_name": "并查集", "category": "ds", "stage": 4, "prerequisite_tags": '["array"]'},
    {"name": "heap", "display_name": "堆", "category": "ds", "stage": 4, "prerequisite_tags": '["array"]'},
    {"name": "sparse_table", "display_name": "ST表", "category": "ds", "stage": 4, "prerequisite_tags": '["array", "prefix_sum"]'},
    {"name": "bit", "display_name": "树状数组", "category": "ds", "stage": 4, "prerequisite_tags": '["array", "prefix_sum"]'},
    {"name": "segment_tree", "display_name": "线段树", "category": "ds", "stage": 4, "prerequisite_tags": '["recursion", "array"]'},
    {"name": "monotone_stack", "display_name": "单调栈", "category": "ds", "stage": 4, "prerequisite_tags": '["stack"]'},
    {"name": "monotone_queue", "display_name": "单调队列", "category": "ds", "stage": 4, "prerequisite_tags": '["queue"]'},
    {"name": "combinatorics", "display_name": "组合数学", "category": "math", "stage": 4, "prerequisite_tags": '["number_theory_basic"]'},
    {"name": "inclusion_exclusion", "display_name": "容斥原理", "category": "math", "stage": 4, "prerequisite_tags": '["combinatorics"]'},
    {"name": "fast_power", "display_name": "快速幂", "category": "math", "stage": 4, "prerequisite_tags": '["recursion"]'},
    {"name": "modular_inverse", "display_name": "逆元", "category": "math", "stage": 4, "prerequisite_tags": '["fast_power", "number_theory_basic"]'},
    {"name": "kmp", "display_name": "KMP字符串匹配", "category": "string", "stage": 4, "prerequisite_tags": '["string_processing"]'},
    {"name": "trie", "display_name": "Trie字典树", "category": "string", "stage": 4, "prerequisite_tags": '["string_processing"]'},
    {"name": "string_hash", "display_name": "字符串哈希", "category": "string", "stage": 4, "prerequisite_tags": '["string_processing"]'},

    # Stage 5: 省选
    {"name": "balanced_tree", "display_name": "平衡树(Treap/Splay)", "category": "ds", "stage": 5, "prerequisite_tags": '["segment_tree"]'},
    {"name": "persistent_ds", "display_name": "可持久化数据结构(主席树)", "category": "ds", "stage": 5, "prerequisite_tags": '["segment_tree"]'},
    {"name": "heavy_light", "display_name": "树链剖分", "category": "ds", "stage": 5, "prerequisite_tags": '["segment_tree", "dfs", "lca"]'},
    {"name": "centroid_decomposition", "display_name": "点分治/边分治", "category": "ds", "stage": 5, "prerequisite_tags": '["dfs", "graph_basic"]'},
    {"name": "suffix_array", "display_name": "后缀数组", "category": "string", "stage": 5, "prerequisite_tags": '["string_hash", "sort_advanced"]'},
    {"name": "suffix_automaton", "display_name": "后缀自动机", "category": "string", "stage": 5, "prerequisite_tags": '["string_processing"]'},
    {"name": "ac_automaton", "display_name": "AC自动机", "category": "string", "stage": 5, "prerequisite_tags": '["trie", "kmp", "bfs"]'},
    {"name": "network_flow", "display_name": "网络流(最大流/费用流)", "category": "graph", "stage": 5, "prerequisite_tags": '["shortest_path", "graph_basic"]'},
    {"name": "bipartite_matching", "display_name": "二分图匹配", "category": "graph", "stage": 5, "prerequisite_tags": '["graph_basic", "dfs"]'},
    {"name": "dp_probability", "display_name": "概率DP/期望DP", "category": "dp", "stage": 5, "prerequisite_tags": '["dp_linear"]'},
    {"name": "game_theory", "display_name": "博弈论(SG函数)", "category": "math", "stage": 5, "prerequisite_tags": '["dp_linear"]'},
    {"name": "cdq_divide", "display_name": "CDQ分治", "category": "ds", "stage": 5, "prerequisite_tags": '["bit", "sort_advanced"]'},
    {"name": "overall_binary", "display_name": "整体二分", "category": "ds", "stage": 5, "prerequisite_tags": '["binary_search", "bit"]'},
    {"name": "matrix_power", "display_name": "矩阵快速幂", "category": "math", "stage": 5, "prerequisite_tags": '["fast_power", "dp_linear"]'},
    {"name": "gaussian_elimination", "display_name": "高斯消元", "category": "math", "stage": 5, "prerequisite_tags": '["array"]'},

    # Stage 6: NOI
    {"name": "fft_ntt", "display_name": "多项式(FFT/NTT)", "category": "math", "stage": 6, "prerequisite_tags": '["fast_power"]'},
    {"name": "advanced_flow", "display_name": "高级网络流", "category": "graph", "stage": 6, "prerequisite_tags": '["network_flow"]'},
    {"name": "virtual_tree", "display_name": "虚树", "category": "ds", "stage": 6, "prerequisite_tags": '["lca", "heavy_light"]'},
    {"name": "sam", "display_name": "SAM后缀自动机", "category": "string", "stage": 6, "prerequisite_tags": '["suffix_automaton"]'},
    {"name": "palindrome_automaton", "display_name": "回文自动机", "category": "string", "stage": 6, "prerequisite_tags": '["string_processing"]'},
    {"name": "lct", "display_name": "Link-Cut Tree", "category": "ds", "stage": 6, "prerequisite_tags": '["balanced_tree"]'},
    {"name": "dp_plug", "display_name": "插头DP", "category": "dp", "stage": 6, "prerequisite_tags": '["dp_bitmask"]'},
    {"name": "cactus_graph", "display_name": "仙人掌图", "category": "graph", "stage": 6, "prerequisite_tags": '["tarjan_scc"]'},
    {"name": "du_sieve", "display_name": "杜教筛", "category": "math", "stage": 6, "prerequisite_tags": '["number_theory_basic"]'},
    {"name": "min25_sieve", "display_name": "Min-25筛", "category": "math", "stage": 6, "prerequisite_tags": '["number_theory_basic"]'},
    {"name": "computational_geometry", "display_name": "高级计算几何", "category": "math", "stage": 6},
]


def seed_tags():
    """Seed all knowledge point tags."""
    app = create_app()
    with app.app_context():
        existing_count = Tag.query.count()
        if existing_count > 0:
            print(f"Tags table already has {existing_count} entries. Skipping seed.")
            print("To re-seed, delete existing tags first.")
            return

        for tag_data in TAGS:
            tag = Tag(
                name=tag_data['name'],
                display_name=tag_data['display_name'],
                category=tag_data.get('category', 'other'),
                stage=tag_data.get('stage', 1),
                prerequisite_tags=tag_data.get('prerequisite_tags'),
            )
            db.session.add(tag)

        db.session.commit()
        print(f"Seeded {len(TAGS)} knowledge point tags across 6 stages.")

        # Print summary
        for stage in range(1, 7):
            stage_tags = [t for t in TAGS if t.get('stage') == stage]
            stage_names = {1: '语法基础', 2: '基础算法', 3: 'CSP-J', 4: 'CSP-S', 5: '省选', 6: 'NOI'}
            print(f"  Stage {stage} ({stage_names[stage]}): {len(stage_tags)} tags")


if __name__ == '__main__':
    seed_tags()
