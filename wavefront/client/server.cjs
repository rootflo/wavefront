const compression = require('compression');
const crypto = require('crypto');
const express = require('express');
const path = require('path');

const PORT = process.env.PORT || 3000;
const NAMESPACE = process.env.NAMESPACE || 'staging-aws';
const BASE_URL = process.env.BASE_URL || `https://${NAMESPACE}.rootflo.ai/floconsole`;
const APP_ENV = process.env.APP_ENV || 'production';
const FEATURE_API_SERVICES = process.env.FEATURE_API_SERVICES || 'false';

const app = express();

// Enable compression for all responses
app.use(compression());

const staticOptions = {
  maxAge: '7d',
  etag: true,
  lastModified: true,
};

app.get('/config.js', (req, res) => {
  const config = {
    BASE_URL,
    APP_ENV,
    FEATURE_API_SERVICES,
  };

  res.setHeader('Content-Type', 'application/javascript');
  res.set({
    'X-Content-Type-Options': 'nosniff',
    'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
  });
  res.send(`window.__APP_CONFIG__ = ${JSON.stringify(config)};`);
});

app.use((req, res, next) => {
  if (req.url === '/' || req.url.endsWith('index.html')) {
    //Stop caching index.html
    return next();
  }
  res.set({
    'X-Content-Type-Options': 'nosniff',
    'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
  });
  express.static(path.join(__dirname, 'dist'), staticOptions)(req, res, next);
});

app.get('*', (req, res) => {
  // Generate nonce for CSP
  const nonce = crypto.randomBytes(16).toString('base64');
  const defaultSrc = `'self'`;
  const connectSrc = `'self' ${new URL(BASE_URL).origin}`;
  const scriptSrc = `'self' 'nonce-${nonce}'`;
  const styleSrc = `'self' 'unsafe-inline'`;
  const mediaSrc = `'self' https://storage.googleapis.com https://*.s3.amazonaws.com`;
  const frameAncestors = 'none';
  const imgSrc = `'self' https://storage.googleapis.com data:`;

  res.set({
    'Cache-Control': 'no-store, no-cache, must-revalidate, private',
    Pragma: 'no-cache',
    Expires: '0',
    'Content-Security-Policy': `default-src ${defaultSrc}; connect-src ${connectSrc} script-src ${scriptSrc}; style-src ${styleSrc}; frame-ancestors ${frameAncestors}; img-src ${imgSrc}; media-src ${mediaSrc}`,
    'X-Content-Type-Options': 'nosniff',
    'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
  });
  res.setHeader('X-Frame-Options', 'DENY');

  // Read the index.html file
  const indexPath = path.join(__dirname, 'dist', 'index.html');
  const indexContent = require('fs').readFileSync(indexPath, 'utf8');

  // Add nonce to script tags
  const modifiedContent = indexContent.replace(/<script/g, `<script nonce="${nonce}"`);

  res.send(modifiedContent);
});

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
