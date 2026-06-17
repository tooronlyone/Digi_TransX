import TransporterFooter from './TransporterFooter'
import TransporterLayout from './TransporterLayout'

function toReadableLabel(value) {
  return value
    .replace(/\.html$/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function toTitleCase(value) {
  return toReadableLabel(value).replace(/\b\w/g, char => char.toUpperCase())
}

function resolveMeta(source = '') {
  if (!source) {
    return {
      folder: 'Transporter',
      title: 'Transporter',
    }
  }

  const parts = source.split('/')
  const folder = parts.length > 1 ? parts[parts.length - 2] : 'Transporter'
  const file = parts[parts.length - 1] || ''

  return {
    folder: toTitleCase(folder),
    title: toTitleCase(file),
  }
}

export function createTransporterPlaceholderPage(source) {
  function TransporterHtmlPage() {
    return <TransporterPlaceholderPage source={source} />
  }

  const meta = resolveMeta(source)
  TransporterHtmlPage.displayName = `${meta.folder}${meta.title}`.replace(/\s+/g, '')
  return TransporterHtmlPage
}

export default function TransporterPlaceholderPage({
  source = '',
  title,
  description = 'Placeholder React page created from the transporter HTML file inventory.',
}) {
  const meta = resolveMeta(source)
  const pageTitle = title || meta.title

  return (
    <TransporterLayout>
      <section className="t-page-card">
        <div className="t-page-eyebrow">{meta.folder}</div>
        <h1 className="t-page-title">{pageTitle}</h1>
        <p className="t-page-description">{description}</p>
        {source && (
          <div className="t-page-meta">
            <span>Source HTML</span>
            <code>{source}</code>
          </div>
        )}
      </section>
      <TransporterFooter />
    </TransporterLayout>
  )
}
