import React, { useState, useRef, useEffect } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from '@aws-sdk/client-bedrock-agentcore'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ApiService from '../services/api'
import ChartRenderer from './ChartRenderer'
import styles from './AgentChat.module.css'

function AgentChat() {
  // Quick action questions for easy user interaction
  const quickActions = [
    { 
      id: 'market-trends', 
      icon: "📊", 
      label: "Market Trends", 
      question: "What are the current real estate market trends in Boston?" 
    },
    { 
      id: 'roi-calculator', 
      icon: "💰", 
      label: "ROI Calculator", 
      question: "How do I calculate ROI for a rental property investment?" 
    },
    { 
      id: 'property-value', 
      icon: "🏠", 
      label: "Property Value", 
      question: "What factors affect property valuation in today's market?" 
    },
    { 
      id: 'investment-tips', 
      icon: "📈", 
      label: "Investment Tips", 
      question: "What are the best real estate investment strategies for 2024?" 
    },
    { 
      id: 'portfolio', 
      icon: "🎯", 
      label: "Portfolio", 
      question: "How should I diversify my real estate investment portfolio?" 
    },
    { 
      id: 'risk-analysis', 
      icon: "📉", 
      label: "Risk Analysis", 
      question: "What are the main risks in real estate investing and how to mitigate them?" 
    }
  ]

  // Get deployment-specific localStorage key
  const getStorageKey = () => {
    const deploymentId = ApiService.getDeploymentId()
    return `bda-chat-history-${deploymentId}`
  }

  const getInitialMessage = () => ({
    id: 1,
    type: 'agent',
    content: '__INITIAL_GREETING__',
    timestamp: new Date()
  })

  const [messages, setMessages] = useState(() => {
    // Load chat history from deployment-specific localStorage key
    const storageKey = getStorageKey()
    const saved = localStorage.getItem(storageKey)
    
    if (saved) {
      try {
        const parsedMessages = JSON.parse(saved)
        // Convert timestamp strings back to Date objects
        return parsedMessages.map(msg => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }))
      } catch (error) {
        console.warn('Error parsing saved chat history:', error)
        // Clear corrupted data
        localStorage.removeItem(storageKey)
      }
    }
    
    return [getInitialMessage()]
  })
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sessionId] = useState(() => `session-${Date.now()}`)
  const [showQuickActions, setShowQuickActions] = useState(() => {
    // Show quick actions initially only if there's just the welcome message
    const storageKey = getStorageKey()
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      try {
        const parsedMessages = JSON.parse(saved)
        return parsedMessages.length <= 1
      } catch {
        return true
      }
    }
    return true
  })
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const messagesContainerRef = useRef(null)

  // Save chat history to deployment-specific localStorage whenever messages change
  useEffect(() => {
    const storageKey = getStorageKey()
    localStorage.setItem(storageKey, JSON.stringify(messages))
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
    }
  }, [inputValue])

  const sendMessage = async () => {
    if (!inputValue.trim() || loading) return

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: inputValue.trim(),
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setLoading(true)
    setError('')

    // Create a placeholder message for streaming
    const streamingMessageId = Date.now() + 1
    const placeholderMessage = {
      id: streamingMessageId,
      type: 'agent',
      content: '',
      timestamp: new Date()
    }
    setMessages(prev => [...prev, placeholderMessage])

    try {
      const session = await fetchAuthSession()
      const credentials = session.credentials

      // Get AgentCore runtime ARN from environment
      const agentRuntimeArn = import.meta.env.VITE_AGENTCORE_RUNTIME_ARN

      if (!agentRuntimeArn) {
        throw new Error('AgentCore runtime ARN not configured. Please set VITE_AGENTCORE_RUNTIME_ARN in your .env file.')
      }

      // Create BedrockAgentCore client
      const agentCoreClient = new BedrockAgentCoreClient({
        region: import.meta.env.VITE_AWS_REGION,
        credentials: {
          accessKeyId: credentials.accessKeyId,
          secretAccessKey: credentials.secretAccessKey,
          sessionToken: credentials.sessionToken
        }
      })

      // Prepare the invocation command
      const command = new InvokeAgentRuntimeCommand({
        agentRuntimeArn: agentRuntimeArn,
        payload: JSON.stringify({
          input: userMessage.content,
          sessionId: sessionId,
          context: {},
          parameters: {}
        })
      })

      // Invoke the agent runtime
      const response = await agentCoreClient.send(command)

      // Handle streaming response
      let accumulatedText = ''
      if (response.response) {
        try {
          // Convert to ReadableStream for streaming
          const stream = response.response.transformToWebStream()
          const reader = stream.getReader()
          const decoder = new TextDecoder()

          while (true) {
            const { done, value } = await reader.read()

            if (done) {
              break
            }

            // Decode the chunk
            const chunk = decoder.decode(value, { stream: true })
            accumulatedText += chunk

            // Try to parse as JSON to extract the response field
            let displayText = accumulatedText
            try {
              const parsed = JSON.parse(accumulatedText)
              if (parsed.response) {
                displayText = parsed.response
              }
            } catch {
              // Not valid JSON yet or plain text response, use as-is
              displayText = accumulatedText
            }

            // Update the message in real-time
            setMessages(prev => prev.map(msg =>
              msg.id === streamingMessageId
                ? { ...msg, content: displayText }
                : msg
            ))
          }

          reader.releaseLock()

          // Final parsing attempt
          let finalText = accumulatedText
          try {
            const parsed = JSON.parse(accumulatedText)
            finalText = parsed.response || accumulatedText
          } catch {
            // Use accumulated text as-is
            finalText = accumulatedText
          }

          // Ensure final message is set
          setMessages(prev => prev.map(msg =>
            msg.id === streamingMessageId
              ? { ...msg, content: finalText || 'I apologize, but I encountered an issue processing your request. Please try again.' }
              : msg
          ))
        } catch (error) {
          console.error('Error streaming response:', error)
          setMessages(prev => prev.map(msg =>
            msg.id === streamingMessageId
              ? { ...msg, content: 'Received response but could not parse it properly.' }
              : msg
          ))
        }
      } else {
        setMessages(prev => prev.map(msg =>
          msg.id === streamingMessageId
            ? { ...msg, content: 'I received your message but could not generate a proper response.' }
            : msg
        ))
      }
    } catch (err) {
      console.error('Error invoking agent:', err)
      setError('Failed to get response from AI agent. Please try again.')

      setMessages(prev => prev.map(msg =>
        msg.id === streamingMessageId
          ? { ...msg, content: 'I apologize, but I encountered an error. Please try your question again.' }
          : msg
      ))
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearChatHistory = () => {
    const initialMessage = getInitialMessage()
    setMessages([initialMessage])
    const storageKey = getStorageKey()
    localStorage.setItem(storageKey, JSON.stringify([initialMessage]))
  }

  const handleQuickAction = (question) => {
    setInputValue(question)
    setShowQuickActions(false)
    // Focus on textarea for immediate sending
    setTimeout(() => {
      textareaRef.current?.focus()
    }, 100)
  }

  // Clean up old chat histories from previous deployments
  useEffect(() => {
    const currentKey = getStorageKey()
    const keysToRemove = []
    
    // Find and remove old BDA chat histories
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.startsWith('bda-chat-history-') && key !== currentKey) {
        keysToRemove.push(key)
      }
    }
    
    keysToRemove.forEach(key => localStorage.removeItem(key))
  }, [])

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
  }

  const formatTime = (date) => {
    return date.toLocaleTimeString('en-US', { 
      hour: 'numeric', 
      minute: '2-digit',
      hour12: true 
    })
  }

  return (
    <div className={styles.chatContainer}>
      {/* Header */}
      <div className={styles.chatHeader}>
        <h2 className={styles.chatTitle}>AI Investment Advisor</h2>
        <button className={styles.clearButton} onClick={clearChatHistory}>
          <span>🗑️</span> Clear History
        </button>
      </div>

      {/* Error Alert */}
      {error && (
        <div className={styles.errorAlert}>
          <span>{error}</span>
          <span className={styles.errorDismiss} onClick={() => setError('')}>✕</span>
        </div>
      )}

      {/* Messages Container */}
      <div className={styles.messagesContainer} ref={messagesContainerRef}>
        {messages.map((message) => (
          <div key={message.id} className={styles.messageGroup}>
            <div className={`${styles.messageWrapper} ${message.type === 'user' ? styles.messageWrapperUser : ''}`}>
              {/* Avatar */}
              <div className={`${styles.avatar} ${message.type === 'agent' ? styles.avatarAI : styles.avatarUser}`}>
                {message.type === 'agent' ? 'AI' : 'You'}
              </div>
              
              {/* Message Bubble */}
              <div className={`${styles.messageBubble} ${message.type === 'agent' ? styles.messageBubbleAI : styles.messageBubbleUser}`}>
                <div className={styles.messageContent}>
                  {message.type === 'agent' ? (
                    message.content === '__INITIAL_GREETING__' ? (
                      <div>
                        <p style={{ margin: '0 0 20px 0', lineHeight: '1.8', fontSize: '15px' }}>
                          Hello! I'm your AI assistant specializing in real estate market analysis and investment strategies. I can help you with:
                        </p>
                        <div className={styles.welcomeFeaturesGrid}>
                          <div style={{
                            background: 'var(--color-surface)',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            padding: '12px',
                            textAlign: 'center',
                            transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)'
                          }}>
                            <div style={{ fontSize: '20px', marginBottom: '6px' }}>📊</div>
                            <div style={{ fontWeight: '600', fontSize: '13px', color: 'var(--color-text-primary)', marginBottom: '4px' }}>Market Analysis</div>
                            <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', lineHeight: '1.3' }}>Current trends, pricing, and forecasts</div>
                          </div>
                          <div style={{
                            background: 'var(--color-surface)',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            padding: '12px',
                            textAlign: 'center',
                            transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)'
                          }}>
                            <div style={{ fontSize: '20px', marginBottom: '6px' }}>💼</div>
                            <div style={{ fontWeight: '600', fontSize: '13px', color: 'var(--color-text-primary)', marginBottom: '4px' }}>Investment Strategies</div>
                            <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', lineHeight: '1.3' }}>Portfolio optimization and risk assessment</div>
                          </div>
                          <div style={{
                            background: 'var(--color-surface)',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            padding: '12px',
                            textAlign: 'center',
                            transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)'
                          }}>
                            <div style={{ fontSize: '20px', marginBottom: '6px' }}>🏠</div>
                            <div style={{ fontWeight: '600', fontSize: '13px', color: 'var(--color-text-primary)', marginBottom: '4px' }}>Property Valuation</div>
                            <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', lineHeight: '1.3' }}>Comparative market analysis</div>
                          </div>
                          <div style={{
                            background: 'var(--color-surface)',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            padding: '12px',
                            textAlign: 'center',
                            transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)'
                          }}>
                            <div style={{ fontSize: '20px', marginBottom: '6px' }}>💰</div>
                            <div style={{ fontWeight: '600', fontSize: '13px', color: 'var(--color-text-primary)', marginBottom: '4px' }}>Financial Calculations</div>
                            <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', lineHeight: '1.3' }}>ROI, cap rates, and more</div>
                          </div>
                        </div>
                        <p style={{ margin: '20px 0 0 0', lineHeight: '1.8', fontSize: '15px' }}>
                          What would you like to explore today?
                        </p>
                      </div>
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ children }) => <p style={{ margin: '12px 0', lineHeight: '1.8' }}>{children}</p>,
                          br: () => <br style={{ margin: '8px 0' }} />,
                          ul: ({ children }) => <ul style={{ display: 'block', margin: '16px 0', paddingLeft: '0', listStyle: 'none' }}>{children}</ul>,
                          li: ({ children }) => <li style={{ display: 'block', margin: '12px 0', lineHeight: '1.8', position: 'relative', paddingLeft: '20px' }}>{children}</li>,
                          code: ({ node, inline, className, children, ...props }) => {
                            const match = /language-chart:(\w+)/.exec(className || '')
                            const isChart = match && !inline

                            if (isChart) {
                              const chartType = match[1]
                              try {
                                const chartData = JSON.parse(String(children).trim())
                                return (
                                  <ChartRenderer
                                    chartData={chartData}
                                    chartType={chartType}
                                  />
                                )
                              } catch (error) {
                                console.error('Error parsing chart data:', error)
                                return (
                                  <div style={{
                                    padding: '12px',
                                    background: '#fee2e2',
                                    border: '1px solid #fca5a5',
                                    borderRadius: '8px',
                                    color: '#dc2626',
                                    fontSize: '14px'
                                  }}>
                                    Error parsing chart data
                                  </div>
                                )
                              }
                            }

                            // Regular code block
                            if (!inline) {
                              return (
                                <pre style={{
                                  background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
                                  padding: '16px',
                                  borderRadius: '12px',
                                  overflow: 'auto',
                                  margin: '16px 0',
                                  border: '1px solid rgba(148, 163, 184, 0.1)',
                                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)'
                                }}>
                                  <code
                                    style={{
                                      background: 'transparent',
                                      padding: 0,
                                      color: '#e2e8f0',
                                      border: 'none',
                                      boxShadow: 'none',
                                      fontSize: '14px',
                                      fontFamily: "'SF Mono', Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace"
                                    }}
                                    {...props}
                                  >
                                    {children}
                                  </code>
                                </pre>
                              )
                            }

                            // Inline code
                            return (
                              <code
                                style={{
                                  background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                                  padding: '4px 10px',
                                  borderRadius: '7px',
                                  fontFamily: "'SF Mono', Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                                  fontSize: '13.5px',
                                  color: '#1e40af',
                                  border: '1px solid rgba(59, 130, 246, 0.2)',
                                  boxShadow: '0 1px 3px rgba(59, 130, 246, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.6)'
                                }}
                                {...props}
                              >
                                {children}
                              </code>
                            )
                          }
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    )
                  ) : (
                    message.content
                  )}
                </div>

                {/* Timestamp and Actions */}
                <div className={styles.messageFooter}>
                  <div className={`${styles.timestamp} ${message.type === 'user' ? styles.timestampUser : ''}`}>
                    <span>{formatTime(message.timestamp)}</span>
                  </div>
                  {message.type === 'agent' && message.content !== '__INITIAL_GREETING__' && (
                    <button
                      className={styles.copyButton}
                      onClick={() => copyToClipboard(message.content)}
                      title="Copy to clipboard"
                    >
                      Copy
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
        
        {/* Typing Indicator */}
        {loading && (
          <div className={styles.typingIndicator}>
            <div className={`${styles.avatar} ${styles.avatarAI}`}>AI</div>
            <div className={styles.typingDots}>
              <span className={styles.typingDot}></span>
              <span className={styles.typingDot}></span>
              <span className={styles.typingDot}></span>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Quick Actions */}
      {showQuickActions && (
        <div className={styles.quickActionsContainer}>
          <div className={styles.quickActionsHeader}>
            <h3>Quick Questions</h3>
            <button
              className={styles.closeQuickActions}
              onClick={() => setShowQuickActions(false)}
              aria-label="Hide quick actions"
            >
              ✕
            </button>
          </div>
          <div className={styles.quickActionsGrid}>
            {quickActions.map((action) => (
              <button
                key={action.id}
                className={styles.quickActionButton}
                onClick={() => handleQuickAction(action.question)}
                disabled={loading}
              >
                <span className={styles.quickActionIcon}>{action.icon}</span>
                <span className={styles.quickActionLabel}>{action.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Container */}
      <div className={styles.inputContainer}>
        <div className={styles.inputWrapper}>
          <textarea
            ref={textareaRef}
            className={styles.textInput}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder="Ask about market trends, investment strategies, or property analysis..."
            disabled={loading}
            rows={1}
          />
          <button
            className={styles.sendButton}
            onClick={sendMessage}
            disabled={!inputValue.trim() || loading}
          >
            <span>Send</span>
            <span>→</span>
          </button>
        </div>
        
        {!showQuickActions && (
          <button 
            className={styles.showQuickActionsButton}
            onClick={() => setShowQuickActions(true)}
            disabled={loading}
          >
            <span>💡</span> Show Quick Questions
          </button>
        )}
      </div>

      {/* Session Info */}
      <div className={styles.sessionInfo}>
        Session ID: {sessionId}
      </div>
    </div>
  )
}

export default AgentChat