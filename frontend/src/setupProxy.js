let createProxyMiddleware;
try {
  ({ createProxyMiddleware } = require("http-proxy-middleware"));
} catch (error) {
  ({ createProxyMiddleware } = require("react-scripts/node_modules/http-proxy-middleware"));
}

module.exports = function (app) {
  app.use(
    "/api",
    createProxyMiddleware({
      target: process.env.API_PROXY_TARGET || "http://localhost:8001",
      changeOrigin: false,
    })
  );
};
