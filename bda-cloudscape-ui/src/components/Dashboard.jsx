import React, { useState, useEffect } from 'react'
import DocumentUpload from './DocumentUpload'
import ProcessingStatus from './ProcessingStatus'
import AgentChat from './AgentChat'
import Analytics from './Analytics'
import ApiService from '../services/api'
import styles from './Dashboard.module.css'

function Dashboard({ user }) {
  const [activeView, setActiveView] = useState('chat')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [stats, setStats] = useState([])
  const [quickStats, setQuickStats] = useState({})
  const [loading, setLoading] = useState(true)

  const navigationItems = [
    { id: 'chat', label: 'AI Agent Chat', icon: '💬', badge: null },
    { id: 'upload', label: 'Upload Documents', icon: '📄', badge: null },
    { id: 'status', label: 'Processing Status', icon: '⚡', badge: null },
    { id: 'analytics', label: 'Analytics', icon: '📊', badge: null },
  ]

  const renderContent = () => {
    switch (activeView) {
      case 'upload':
        return <DocumentUpload />
      case 'status':
        return <ProcessingStatus />
      case 'chat':
        return <AgentChat />
      case 'analytics':
        return <Analytics />
      default:
        return <AgentChat />
    }
  }

  const getPageInfo = () => {
    switch (activeView) {
      case 'upload':
        return {
          title: 'Document Upload',
          description: 'Upload and process your financial documents with AI-powered analysis'
        }
      case 'status':
        return {
          title: 'Processing Status',
          description: 'Monitor the status of your document processing pipeline'
        }
      case 'chat':
        return {
          title: 'AI Investment Advisor',
          description: 'Get real-time market insights and investment recommendations'
        }
      case 'analytics':
        return {
          title: 'Analytics Dashboard',
          description: 'Visualize your portfolio performance and market trends'
        }
      default:
        return {
          title: 'Dashboard',
          description: 'Welcome to your investment platform'
        }
    }
  }

  const pageInfo = getPageInfo()

  // Load dashboard metrics on component mount
  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true)
        const [metricsData, quickStatsData] = await Promise.all([
          ApiService.getDashboardMetrics(),
          ApiService.getQuickStats()
        ])
        setStats(metricsData)
        setQuickStats(quickStatsData)
      } catch (error) {
        console.error('Error loading dashboard data:', error)
        // Set default values on error
        setStats([
          { label: 'Documents Processed', value: '0', change: '0%', neutral: true },
          { label: 'Active Analyses', value: '0', change: 'Idle', neutral: true }
        ])
        setQuickStats({ activeProcessing: 0, totalDocuments: 0, serverStatus: 'Online' })
      } finally {
        setLoading(false)
      }
    }

    loadDashboardData()
  }, [])

  return (
    <div className={styles.dashboardContainer}>
      {/* Sidebar Navigation */}
      <nav className={`${styles.sidebar} ${mobileMenuOpen ? styles.open : ''}`}>
        <div className={styles.sidebarHeader}>
          <div className={styles.sidebarTitle}>Navigation</div>
        </div>
        
        {navigationItems.map(item => (
          <button
            key={item.id}
            className={`${styles.navItem} ${activeView === item.id ? styles.active : ''}`}
            onClick={() => {
              setActiveView(item.id)
              setMobileMenuOpen(false)
            }}
          >
            <span className={styles.navIcon}>{item.icon}</span>
            <span>{item.label}</span>
            {item.badge && (
              <span className={styles.navBadge}>{item.badge}</span>
            )}
          </button>
        ))}
        
        <div style={{ marginTop: 'auto', paddingTop: '20px', borderTop: '1px solid var(--color-border)' }}>
          <div className={styles.sidebarHeader}>
            <div className={styles.sidebarTitle}>Quick Stats</div>
          </div>
          <div style={{ padding: '0 16px', fontSize: '14px', color: 'var(--color-text-secondary)' }}>
            <div style={{ marginBottom: '8px' }}>
              <strong>Active Processing:</strong> {quickStats.activeProcessing || 0}
            </div>
            <div style={{ marginBottom: '8px' }}>
              <strong>Total Documents:</strong> {quickStats.totalDocuments || 0}
            </div>
            <div>
              <strong>Server Status:</strong> <span style={{ color: '#2ea043' }}>● {quickStats.serverStatus || 'Online'}</span>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className={styles.mainContent}>
        {/* Show stats only on dashboard home (chat) */}
        {activeView === 'chat' && (
          <>
            <div className={styles.contentHeader}>
              <h1 className={styles.pageTitle}>{pageInfo.title}</h1>
              <p className={styles.pageDescription}>{pageInfo.description}</p>
            </div>

            {/* Quick Actions */}
            <div className={styles.quickActions}>
              <button 
                className={styles.actionButton}
                onClick={() => setActiveView('upload')}
              >
                <span>📤</span> Upload New Document
              </button>
              <button 
                className={`${styles.actionButton} ${styles.secondary}`}
                onClick={() => setActiveView('analytics')}
              >
                <span>📈</span> View Analytics
              </button>
              <button 
                className={`${styles.actionButton} ${styles.secondary}`}
                onClick={() => setActiveView('status')}
              >
                <span>🔍</span> Check Status
              </button>
            </div>

            {/* Stats Grid */}
            <div className={styles.statsGrid}>
              {loading ? (
                Array.from({ length: 2 }).map((_, index) => (
                  <div key={index} className={styles.statCard}>
                    <div className={styles.statLabel}>Loading...</div>
                    <div className={styles.statValue}>--</div>
                    <div className={styles.statChange}>--</div>
                  </div>
                ))
              ) : (
                stats.map((stat, index) => (
                  <div 
                    key={index} 
                    className={`${styles.statCard} ${
                      stat.positive ? styles.success : 
                      stat.negative ? styles.danger : ''
                    }`}
                  >
                    <div className={styles.statLabel}>{stat.label}</div>
                    <div className={styles.statValue}>{stat.value}</div>
                    <div className={`${styles.statChange} ${
                      stat.positive ? styles.positive : 
                      stat.negative ? styles.negative : ''
                    }`}>
                      {stat.positive && '↑'}
                      {stat.negative && '↓'}
                      {stat.change}
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}

        {/* Render Active Component */}
        <div className={styles.contentCard}>
          {renderContent()}
        </div>
      </main>

      {/* Mobile Menu Toggle */}
      <button
        className={styles.mobileMenuToggle}
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        style={{
          display: 'none', // Show only on mobile via media query
          position: 'fixed',
          bottom: '20px',
          right: '20px',
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          background: 'var(--gradient-primary)',
          color: 'white',
          border: 'none',
          boxShadow: 'var(--shadow-lg)',
          cursor: 'pointer',
          fontSize: '24px',
          zIndex: 'var(--z-fixed)'
        }}
      >
        ☰
      </button>
    </div>
  )
}

export default Dashboard