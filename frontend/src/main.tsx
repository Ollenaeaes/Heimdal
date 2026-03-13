import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

// NOTE: StrictMode intentionally omitted — Cesium's Viewer.destroy() is
// irreversible, so the double-mount/unmount cycle in StrictMode kills the
// WebGL context and the globe never renders.
// CESIUM_BASE_URL is set via Vite `define` in vite.config.ts (compile-time).

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
