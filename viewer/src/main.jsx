import { createRoot } from 'react-dom/client'
import React from 'react'
import App from './App'
import './styles.css'

class RootErrorBoundary extends React.Component {
	constructor(props) {
		super(props)
		this.state = { error: null }
	}

	static getDerivedStateFromError(error) {
		return { error }
	}

	componentDidCatch(error) {
		console.error('Viewer runtime error:', error)
	}

	render() {
		if (!this.state.error) {
			return this.props.children
		}

		return (
			<div style={{
				minHeight: '100vh',
				display: 'flex',
				flexDirection: 'column',
				alignItems: 'center',
				justifyContent: 'center',
				padding: 24,
				background: '#f8f9fa',
				color: '#111',
				fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
			}}>
				<h2 style={{ marginBottom: 8 }}>Viewer runtime fout</h2>
				<p style={{ marginBottom: 12, color: '#444' }}>
					De UI is niet geladen door een JavaScript-fout. Herlaad de pagina of start de viewer opnieuw.
				</p>
				<pre style={{
					width: '100%',
					maxWidth: 860,
					padding: 12,
					border: '1px solid #ddd',
					background: '#fff',
					overflow: 'auto',
					whiteSpace: 'pre-wrap',
					wordBreak: 'break-word',
				}}>
					{String(this.state.error?.stack || this.state.error?.message || this.state.error)}
				</pre>
			</div>
		)
	}
}

createRoot(document.getElementById('root')).render(
	<RootErrorBoundary>
		<App />
	</RootErrorBoundary>
)
