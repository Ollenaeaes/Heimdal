import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';

// Set Cesium base URL before any Cesium imports
window.CESIUM_BASE_URL = '/cesium';

import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
