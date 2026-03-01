# Lessons Learned

## 1. Bootstrap 单例 Modal + Promise 竞态条件

**日期**: 2026-02-28
**相关提交**: `92ed399` (Fix ojConfirm race condition when chaining consecutive modals)

### 问题模式

单例 modal 封装为返回 Promise 的函数时，如果在 click handler 中同步 resolve Promise 再异步 hide modal，连续调用会导致第一个 modal 的 `hidden.bs.modal` 事件"偷走"第二个调用的 resolve 回调。

**根因**: Bootstrap `modal.hide()` 是异步的（有动画），但 `resolve()` 是同步的。连续调用时序：

1. 用户点击确认 → click handler 同步 resolve Promise A → 调用 `modal.hide()`
2. 调用方收到 resolve，立即发起下一个 `ojConfirm()` → 绑定新的 `hidden.bs.modal` listener
3. 第一个 modal 的 hide 动画完成 → 触发 `hidden.bs.modal` → 执行的是**第二个调用**的 listener
4. 第二个 modal 还没展示就被"关闭"了

### 规则

单例 UI 组件（modal/dialog/toast）封装为 Promise 时：

- **resolve 时机必须统一到组件完全关闭的事件中**（如 `hidden.bs.modal`）
- 用标志位（如 `confirmed = true/false`）区分确认/取消
- **绝不在 click handler 中同步 resolve 后异步 hide**

### 正确实现模式

```javascript
function ojConfirm(message) {
    return new Promise(resolve => {
        let confirmed = false;

        confirmBtn.onclick = () => { confirmed = true; modal.hide(); };
        cancelBtn.onclick = () => { confirmed = false; modal.hide(); };

        modalEl.addEventListener('hidden.bs.modal', function handler() {
            modalEl.removeEventListener('hidden.bs.modal', handler);
            resolve(confirmed);  // resolve 在动画完全结束后
        });

        modal.show();
    });
}
```

### 通用原则

**异步 UI 动画 + 共享状态 + Promise = 竞态高发区。** 状态变更必须与动画生命周期严格同步。

---

## 2. OJ 爬虫开发经验

**日期**: 2026-02-28
**参考文档**: `app/scrapers/DESIGN.md`

### 2.1 YBT 编码是 UTF-8，不是 GBK

YBT（一本通）是古老的 PHP 系统，但页面编码是 UTF-8。使用 `resp.content.decode('utf-8', errors='replace')`，不要假设 GBK。

**规则**: 不要根据系统年代猜测编码，以实际响应为准。

### 2.2 YBT pshow() 是单参数格式

YBT 题目页面的 `pshow()` 函数只有一个双引号字符串参数：
```javascript
pshow("content with \\n and \\" escapes")
```
不是 `pshow("title", "content")` 双参数格式。正则必须精确匹配单参数。

反转义顺序敏感：先处理 `\\n`/`\\"`/`\\'`，最后处理 `\\\\`。

### 2.3 CTOJ 客户端过滤陷阱

Hydro 的 `/d/{domain}/record?uidOrName={uid}` 已在服务端按用户过滤。不要在客户端再做 uid 匹配过滤——Hydro 返回的 `uid` 是数字 ID 而非用户名，客户端比对会导致所有记录被错误丢弃。

**规则**: 先确认 API 是否已做过滤，再决定是否需要客户端过滤。重复过滤不是安全，是 bug。

### 2.4 Coderlands hash cursor 耦合

Coderlands 使用 hash-based 增量同步，通过 `self._new_cursor` 属性传递自定义 cursor。SyncService 通过 `getattr(scraper, '_new_cursor', None)` 读取。

这是一个隐式耦合点——如果新爬虫也定义了 `_new_cursor` 属性，会被 SyncService 意外消费。

**规则**: 自定义 cursor 机制应在 BaseScraper 中显式声明接口，而非依赖隐式属性。

### 2.5 HOJ JWT Token 位置

BBC OJ (HOJ) 的 JWT Token 在响应头 `Authorization` 中返回，**不带 `Bearer` 前缀**。设置时直接 `session.headers['Authorization'] = token`，加了 `Bearer ` 前缀会导致 401。

**规则**: 不要假设所有 JWT 实现都遵循 `Bearer {token}` 规范。以实际 API 行为为准。

### 2.6 Coderlands getClassWorkOne 只接受 UUID

**日期**: 2026-03-01

`getClassWorkOne?uuid={param}` 的 `uuid` 参数**只接受 32 位十六进制 UUID**，传入题号会返回 HTTP 500（无错误消息）。这导致初版 UUID 解析 Stage 2 对 53 个题号发起 159 次无效 API 调用（53 × 3 重试），全部 500 错误。

**正确做法**：通过课节遍历 (`getlesconNew`) 获取 UUID。`myls` 返回 `result.lessonInfo[]`（不是 `dataList`），每个课节通过 `getlesconNew?uuid={lessonUuid}&classUuid={classUuid}` 获取题目列表，题目 UUID 在 `dataList[].uuid`，题号在 `dataList[].name` 字段（格式 `"P{no} 题目名"`，无独立 `problemNo` 字段）。

**限制**：`myls` 只返回当前班级课节，过去班级的题目 UUID 不可见。

**规则**:
- 不要猜测 API 参数的接受类型，先用诊断脚本验证
- 对未知 API 响应结构，先打印完整响应再写解析代码
- N × retry 的 API 调用模式在参数错误时会放大问题（需有快速失败机制）

### 2.7 通用规则

- **新爬虫上线前**：必须在 `app/scrapers/DESIGN.md` 中记录平台章节
- **修复爬虫 bug 后**：必须在 DESIGN.md 对应平台的"已知陷阱"节追加条目
- **修改 API 路径/字段**：同步更新 DESIGN.md 中的 API 接口表
