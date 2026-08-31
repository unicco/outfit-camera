# Coordinate Recorder UI

React + TypeScript + Vite を使用したコーディネート記録システムのユーザーインターフェース

## 🚀 開発環境セットアップ

### 開発サーバー起動

```bash
npm run dev         # 通常の開発サーバー
npm run dev:fast    # 高速起動（TypeScript チェック最小化）
npm run dev:local   # ローカル開発用設定
```

### ビルド

```bash
npm run build                # 開発用ビルド（ui/dist/ に出力）
npm run build:production     # 本番用ビルド（型チェック付き）
```

## 📁 ビルド出力先

**開発・本番とも `ui/dist/`。** VPS では Caddy がこのディレクトリをそのまま静的配信する（`deploy/caddy/coordinate.caddy` の `root * .../ui/dist`）。

nginx 時代は `/var/www/coordinate-recorder-ui/` へ `www-data` 所有で出力していたが、その経路は使っていない（で `build:deploy` と `scripts/ui-build.sh` ごと削除）。

## 🛠️ Deploy 方法

`deploy/setup-vps.sh` が VPS 上で `npm run build` を実行する。手動で反映するなら VPS 上で同じことをする。

```bash
ssh conoha
cd ~/services/coordinate-recorder/ui
npm run build
```

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type aware lint rules:

- Configure the top-level `parserOptions` property like this:

```js
export default tseslint.config({
  languageOptions: {
    // other options...
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
});
```

- Replace `tseslint.configs.recommended` to `tseslint.configs.recommendedTypeChecked` or `tseslint.configs.strictTypeChecked`
- Optionally add `...tseslint.configs.stylisticTypeChecked`
- Install [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react) and update the config:

```js
// eslint.config.js
import react from 'eslint-plugin-react';

export default tseslint.config({
  // Set the react version
  settings: { react: { version: '18.3' } },
  plugins: {
    // Add the react plugin
    react,
  },
  rules: {
    // other rules...
    // Enable its recommended rules
    ...react.configs.recommended.rules,
    ...react.configs['jsx-runtime'].rules,
  },
});
```
