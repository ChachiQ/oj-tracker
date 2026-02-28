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
