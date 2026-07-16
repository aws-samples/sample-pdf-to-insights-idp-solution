import React from 'react'
import { StatusIndicator, Badge, Box, SpaceBetween } from '@cloudscape-design/components'

const EnhancedStatusIndicator = ({ 
  status = 'pending', 
  showBadge = false, 
  showProgress = false, 
  progress = 0,
  size = 'normal',
  animated = false,
  customStates = {},
  label,
  description,
  ...props 
}) => {
  // Default status mappings
  const defaultStates = {
    pending: { type: 'pending', color: 'grey', label: 'Pending' },
    processing: { type: 'in-progress', color: 'blue', label: 'Processing' },
    completed: { type: 'success', color: 'green', label: 'Completed' },
    failed: { type: 'error', color: 'red', label: 'Failed' },
    cancelled: { type: 'stopped', color: 'grey', label: 'Cancelled' },
    warning: { type: 'warning', color: 'orange', label: 'Warning' }
  }

  const states = { ...defaultStates, ...customStates }
  const currentState = states[status] || states.pending

  const getAnimationStyle = () => {
    if (!animated) return {}
    
    if (status === 'processing') {
      return {
        animation: 'pulse 2s infinite'
      }
    }
    
    return {}
  }

  const renderContent = () => {
    if (showBadge) {
      return (
        <Badge color={currentState.color} className={animated ? 'animated-badge' : ''}>
          {label || currentState.label}
        </Badge>
      )
    }

    return (
      <StatusIndicator 
        type={currentState.type}
        style={getAnimationStyle()}
        {...props}
      >
        {label || currentState.label}
      </StatusIndicator>
    )
  }

  if (description || showProgress) {
    return (
      <SpaceBetween direction="vertical" size="xs">
        {renderContent()}
        {description && (
          <Box variant="small" color="text-body-secondary">
            {description}
          </Box>
        )}
        {showProgress && status === 'processing' && (
          <div style={{ 
            width: '100%', 
            height: '4px', 
            backgroundColor: 'var(--color-border)', 
            borderRadius: 'var(--radius-full)',
            overflow: 'hidden'
          }}>
            <div style={{
              width: `${progress}%`,
              height: '100%',
              backgroundColor: 'var(--color-primary)',
              borderRadius: 'var(--radius-full)',
              transition: 'width 0.3s ease',
              background: 'linear-gradient(90deg, var(--color-primary) 0%, var(--color-primary-dark) 100%)'
            }} />
          </div>
        )}
      </SpaceBetween>
    )
  }

  return renderContent()
}

export default EnhancedStatusIndicator