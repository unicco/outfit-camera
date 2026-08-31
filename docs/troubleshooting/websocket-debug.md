# WebSocket “welcome → 20 ms で close” 調査プレイブック

_2025-06-23_

---

## 背景

- `ws://pi-camera.local:8001/ws` へ接続すると  
  `{"type":"welcome", …}` 受信直後に **code 1005 / 1006 で切断**。
- `wscat` では再現しない → **ブラウザ側 JS が self-close** していると推定。

---

## 調査フロー（TL;DR）

1. **素のブラウザ API** で再現確認
2. **スタックトレース付き close ログ** を仕込む
3. **依存配列・Strict Mode** を最小化したフック骨格へ差し替え
4. それでも切れる場合は **monkey-patch で犯人捕捉**
5. 原因別の対処表を参考に修正

---

## 1 : 素の `WebSocket` で再現するか

```js
// DevTools Console
const ws = new WebSocket("ws://pi-camera.local:8001/ws");
ws.onopen = () => console.log("open");
ws.onclose = (e) => console.log("close", e.code, e.reason);
```
