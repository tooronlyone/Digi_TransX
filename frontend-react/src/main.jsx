import { createRoot } from 'react-dom/client';
import { StrictMode } from 'react';
import '@fortawesome/fontawesome-free/css/all.min.css';
import App from './App.jsx';
import './styles/tailwind.css';
import './styles/global.css';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
