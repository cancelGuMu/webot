import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// --- console easter egg ---
;(function () {
  const c = 'color:#346538;font-size:14px;'
  const b = 'color:#346538;font-size:18px;font-weight:bold;'
  const n = 'color:#787774;font-size:12px;'
  console.log('%c🚣%c  孤舟99 %c— 微信机器人', b, b, n)
  console.log('%c  扁舟一叶，独钓群聊。', c)
  console.log('%c  https://github.com/cancelGuMu/wechat-group-bot', n)
})()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
