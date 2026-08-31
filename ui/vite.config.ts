import path from "path"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig, loadEnv } from "vite"

// .env ファイルから環境変数を読み込み（プロジェクトルートから）
const mode = process.env.NODE_ENV || 'development'
// 本番ビルド時は .env.production を優先的に読み込み
const env = loadEnv(mode, path.resolve(__dirname, '..'), '')

// 環境変数を優先的に使用（デフォルト: 8000）
const finalApiPort = env.VITE_PROXY_API_PORT || env.API_PORT || '8000'
const finalTarget = `http://localhost:${finalApiPort}`

// UIポート設定（動的ポート対応）
const uiPort = parseInt(env.UI_PORT || env.VITE_PORT || '3000')

export default defineConfig({
  plugins: [
    tailwindcss(),
    react({
      // TypeScript処理を最適化
      babel: {
        plugins: [],
      },
      // JSX runtime optimization
      jsxRuntime: 'automatic',
    }),
  ],
  // 環境変数をビルド時に注入
  define: {
    // 本番ビルド時は空文字列を強制（Mixed Content 対策）
    'import.meta.env.VITE_API_URL': mode === 'production' ? '""' : JSON.stringify(env.VITE_API_URL || ''),
    'import.meta.env.VITE_CAMERA_URL': mode === 'production' ? '""' : JSON.stringify(env.VITE_CAMERA_URL || ''),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: '0.0.0.0',
    port: uiPort,
    strictPort: true,
    cors: true,
    allowedHosts: [
      'localhost',
      '127.0.0.1',
      'pi-camera.local',
      'unicco.app',           // メインドメイン
      'coordinate.unicco.app'  // アプリドメイン
    ],
    watch: {
      // ファイル監視の最適化
      ignored: [
        '**/node_modules/**',
        '**/.git/**',
        '**/dist/**',
        '**/build/**',
        '**/coverage/**',
        '**/.DS_Store',
        '**/Thumbs.db',
        // API・カメラ・テストファイルなど、UIに影響しないファイルを除外
        '../api/**',
        '../camera/**',
        '../tests/**',
        '../logs/**',
        '../photos/**',
        '../wardrobe_images/**',
        '../*.log',
        '../*.db',
        '../*.sqlite',
        // より具体的な除外パターン
        '**/*.log',
        '**/*.db',
        '**/*.sqlite',
        '**/*.pyc',
        '**/__pycache__/**',
        '**/venv/**',
        '**/env/**',
        '**/.venv/**',
        '**/.pytest_cache/**',
        '**/.mypy_cache/**',
      ],
      // ポーリング間隔を調整（ファイルシステムによっては効果的）
      usePolling: false,
      // ファイル変更検出の間隔を調整
      interval: 100,
    },
    proxy: {
      '/api': {
        target: finalTarget,
        changeOrigin: true,
      },
      '/camera': {
        target: finalTarget,
        changeOrigin: true,
      },
      '/stream': {
        target: finalTarget,
        changeOrigin: true,
        rewrite: path => path.replace(/^\/stream/, '/camera/stream'),
      },
    }
  },
  // ビルド最適化
  optimizeDeps: {
    // 事前バンドルから除外するパッケージ（必要に応じて）
    exclude: [],
    // よく使うパッケージを事前バンドル
    include: ['react', 'react-dom', 'lucide-react'],
  },
  build: {
    // 環境に応じてビルド出力先を動的設定（権限問題回避）
    outDir: process.env.BUILD_TARGET || 'dist',
    // プロジェクト外への出力時のディレクトリクリーンアップを許可
    emptyOutDir: true,
    // ビルド最適化設定
    target: 'es2020',
    rollupOptions: {
      output: {
        // アセットファイル名の最適化
        assetFileNames: 'assets/[name]-[hash].[ext]',
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
      },
    },
  },
  esbuild: {
    // TypeScript のトランスパイルを高速化
    target: 'es2020',
    // 本番環境でも console は残す（debugger のみ削除）
    drop: ['debugger'],
  },
  // 開発時の追加設定
  ...(mode === 'development' && {
    // 開発時のみの設定を必要に応じて追加
  }),
})
