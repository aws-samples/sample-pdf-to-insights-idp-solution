import React from 'react'
import ReactDOM from 'react-dom/client'
import { Amplify } from 'aws-amplify'
import App from './App.jsx'
import '@cloudscape-design/global-styles/index.css'
import { loadRuntimeConfig } from './config/aws-config'

// Initialize app with runtime configuration
async function initializeApp() {
  // Load runtime configuration from /config.json (or fall back to build-time env vars)
  const config = await loadRuntimeConfig()

  // Configure Amplify with runtime configuration
  const amplifyConfig = {
    Auth: {
      Cognito: {
        userPoolId: config.cognito.userPoolId,
        userPoolClientId: config.cognito.userPoolClientId,
        identityPoolId: config.cognito.identityPoolId,
        region: config.region
      }
    },
    Storage: {
      S3: {
        bucket: config.s3.bucket,
        region: config.region
      }
    }
  }

  console.log('✅ Amplify configured with:', {
    userPoolId: config.cognito.userPoolId,
    identityPoolId: config.cognito.identityPoolId,
    region: config.region,
    bucket: config.s3.bucket,
    configSource: config === (await loadRuntimeConfig()) ? 'runtime' : 'build-time'
  })

  Amplify.configure(amplifyConfig)

  // Render app
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
}

// Start app initialization
initializeApp().catch(error => {
  console.error('Failed to initialize app:', error)
  // Still render app with build-time config as fallback
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
})
