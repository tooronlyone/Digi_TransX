import { createRoot } from 'react-dom/client';
import { StrictMode } from 'react';
import '@fortawesome/fontawesome-free/css/all.min.css';
import App from './App.jsx';
import { installAccessFetchInterceptor } from './auth/accessLock.js';
import './styles/tailwind.css';
import './styles/global.css';

installAccessFetchInterceptor();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
