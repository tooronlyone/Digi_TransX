import { readFileSync } from 'node:fs'

// Source imports (logos/fonts/Leaflet assets) belong to Vite's module graph.
// Only these public URLs are served directly; never recursively copy public/.
export const STATIC_ASSET_NAMES = Object.freeze(['favicon.svg', 'icons.svg'])

export function controlledStaticAssets(publicDirectory = new URL('../public/', import.meta.url)) {
  const assets = new Map(STATIC_ASSET_NAMES.map(name => [`/${name}`, new URL(name, publicDirectory)]))
  const middleware = (request, response, next) => {
    const pathname = String(request.url || '').split('?', 1)[0]
    const source = assets.get(pathname)
    if (!source || !['GET', 'HEAD'].includes(request.method || 'GET')) { next(); return }
    try {
      const bytes = readFileSync(source)
      response.setHeader('Content-Type', 'image/svg+xml')
      response.setHeader('Content-Length', String(bytes.length))
      response.end(request.method === 'HEAD' ? undefined : bytes)
    } catch (error) { next(error) }
  }
  return {
    name: 'digi-transx-static-assets',
    configureServer(server) { server.middlewares.use(middleware) },
    configurePreviewServer(server) { server.middlewares.use(middleware) },
    generateBundle() {
      for (const [pathname, source] of assets) {
        this.emitFile({ type: 'asset', fileName: pathname.slice(1), source: readFileSync(source) })
      }
    },
  }
}
