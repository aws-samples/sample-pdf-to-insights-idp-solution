import React, { useState, useEffect } from 'react'
import { getCurrentUser, signOut, fetchAuthSession } from 'aws-amplify/auth'
import { AppLayout, TopNavigation, Alert } from '@cloudscape-design/components'
import LoginForm from './components/LoginForm'
import Dashboard from './components/Dashboard'
import styles from './components/Login.module.css'
import './styles/premium.css'

function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    checkAuthState()
  }, [])

  const checkAuthState = async () => {
    try {
      const currentUser = await getCurrentUser()
      setUser(currentUser)
    } catch (err) {
      console.log('No authenticated user')
    } finally {
      setLoading(false)
    }
  }

  const handleSignOut = async () => {
    try {
      await signOut()
      setUser(null)
    } catch (err) {
      setError('Error signing out')
    }
  }

  const handleSignIn = async (authenticatedUser) => {
    console.log('=== SIGN IN PROCESS STARTED ===')
    console.log('Authenticated user:', authenticatedUser)

    setUser(authenticatedUser)

    // Give Amplify time to set up tokens
    console.log('Waiting 1 second for token setup...')
    await new Promise(resolve => setTimeout(resolve, 1000))

    try {
      // Try multiple times to get credentials
      let session = null
      let attempts = 0
      const maxAttempts = 5

      while (attempts < maxAttempts) {
        attempts++
        console.log(`Attempt ${attempts}/${maxAttempts} to fetch credentials...`)

        session = await fetchAuthSession({ forceRefresh: true })

        console.log('Attempt', attempts, 'result:', {
          hasCredentials: !!session.credentials,
          hasTokens: !!session.tokens,
          hasIdentityId: !!session.identityId,
          identityId: session.identityId,
          tokens: session.tokens ? {
            accessToken: !!session.tokens.accessToken,
            idToken: !!session.tokens.idToken
          } : null
        })

        if (session.credentials && session.identityId) {
          console.log('✅ SUCCESS! Credentials obtained on attempt', attempts)
          console.log('Identity ID:', session.identityId)
          console.log('Credentials expire:', session.credentials.expiration)
          setError('')
          break
        }

        if (attempts < maxAttempts) {
          console.log(`No credentials yet, waiting 2 seconds before retry...`)
          await new Promise(resolve => setTimeout(resolve, 2000))
        }
      }

      if (!session || !session.credentials || !session.identityId) {
        console.error('❌ FAILED to get credentials after', maxAttempts, 'attempts')
        console.error('Final session state:', {
          hasSession: !!session,
          hasTokens: !!session?.tokens,
          hasCredentials: !!session?.credentials,
          identityId: session?.identityId
        })
        setError('Unable to obtain AWS credentials. Your Identity Pool may not be configured correctly. Contact support.')
      }
    } catch (err) {
      console.error('❌ Error during credential fetch:', err)
      setError('Error obtaining credentials: ' + err.message)
    }

    console.log('=== SIGN IN PROCESS COMPLETED ===')
  }

  if (loading) {
    return (
      <div className={styles.loginPage}>
        <div className={styles.loginContainer}>
          <div className={styles.loadingOverlay}>
            <div className={styles.loadingSpinner}></div>
          </div>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className={styles.loginPage}>
        {error && (
          <div style={{ position: 'absolute', top: '20px', left: '20px', right: '20px', zIndex: 1000 }}>
            <Alert type="error" dismissible onDismiss={() => setError('')}>
              {error}
            </Alert>
          </div>
        )}
        <LoginForm onSignIn={handleSignIn} onError={setError} />
      </div>
    )
  }

  return (
    <div>
      <TopNavigation
        identity={{
          href: '#',
          title: '🏢 BDA Investment Platform',
          logo: { src: '', alt: 'BDA' }
        }}
        utilities={[
          {
            type: 'button',
            text: 'Dashboard',
            href: '#dashboard'
          },
          {
            type: 'menu-dropdown',
            text: user.username,
            iconName: 'user-profile',
            items: [
              { id: 'profile', text: 'Profile Settings' },
              { id: 'divider', text: '-' },
              { id: 'signout', text: 'Sign out' }
            ],
            onItemClick: ({ detail }) => {
              if (detail.id === 'signout') {
                handleSignOut()
              }
            }
          }
        ]}
      />
      <AppLayout
        navigationHide
        content={<Dashboard user={user} />}
        toolsHide
      />
    </div>
  )
}

export default App
