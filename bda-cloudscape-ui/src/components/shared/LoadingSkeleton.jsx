import React from 'react'
import { Box } from '@cloudscape-design/components'

const LoadingSkeleton = ({ 
  width = '100%', 
  height = '20px', 
  borderRadius = 'var(--radius-md)', 
  count = 1,
  className = '',
  ...props 
}) => {
  const skeletons = Array.from({ length: count }, (_, index) => (
    <div
      key={index}
      className={`loading-skeleton ${className}`}
      style={{
        width,
        height,
        borderRadius,
        background: 'linear-gradient(90deg, #f6f8fa 0%, #eaeef2 20%, #f6f8fa 40%, #f6f8fa 100%)',
        backgroundSize: '1000px 100%',
        animation: 'shimmer 2s linear infinite',
        marginBottom: count > 1 && index < count - 1 ? 'var(--spacing-xs)' : '0',
        ...props.style
      }}
      {...props}
    />
  ))

  return count === 1 ? skeletons[0] : (
    <div className="skeleton-container">
      {skeletons}
    </div>
  )
}

// Preset skeleton components for common use cases
export const SkeletonCard = ({ children, loading, ...props }) => {
  if (!loading) return children
  
  return (
    <Box padding="m" style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)' }}>
      <LoadingSkeleton height="24px" width="60%" {...props} />
      <div style={{ marginTop: 'var(--spacing-sm)' }}>
        <LoadingSkeleton height="16px" width="100%" />
      </div>
      <div style={{ marginTop: 'var(--spacing-xs)' }}>
        <LoadingSkeleton height="16px" width="80%" />
      </div>
    </Box>
  )
}

export const SkeletonChart = ({ loading, children, height = '300px', ...props }) => {
  if (!loading) return children
  
  return (
    <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <LoadingSkeleton height="80%" width="90%" {...props} />
    </div>
  )
}

export const SkeletonTable = ({ loading, children, rows = 5, columns = 4, ...props }) => {
  if (!loading) return children
  
  return (
    <div style={{ width: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', gap: 'var(--spacing-md)', marginBottom: 'var(--spacing-md)' }}>
        {Array.from({ length: columns }, (_, i) => (
          <LoadingSkeleton key={i} height="20px" width={`${100/columns}%`} {...props} />
        ))}
      </div>
      
      {/* Rows */}
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={rowIndex} style={{ display: 'flex', gap: 'var(--spacing-md)', marginBottom: 'var(--spacing-sm)' }}>
          {Array.from({ length: columns }, (_, colIndex) => (
            <LoadingSkeleton key={colIndex} height="16px" width={`${100/columns}%`} {...props} />
          ))}
        </div>
      ))}
    </div>
  )
}

export default LoadingSkeleton