import React, { useState } from 'react'
import { 
  Box, 
  Button, 
  SpaceBetween, 
  Header, 
  ButtonDropdown,
  Toggle,
  Popover 
} from '@cloudscape-design/components'
import { 
  ResponsiveContainer,
  BarChart,
  LineChart,
  PieChart,
  Area,
  AreaChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Pie,
  Cell,
  Bar,
  Line
} from 'recharts'

const InteractiveChart = ({
  data = [],
  type = 'bar',
  title,
  description,
  height = 300,
  showExport = true,
  showViewOptions = true,
  customColors = [],
  exportFilename = 'chart-data',
  children,
  ...chartProps
}) => {
  const [viewType, setViewType] = useState(type)
  const [showGrid, setShowGrid] = useState(true)
  const [showLegend, setShowLegend] = useState(true)
  const [animationEnabled, setAnimationEnabled] = useState(true)

  const defaultColors = [
    '#0073bb', '#16a34a', '#dc2626', '#f59e0b', 
    '#7c3aed', '#db2777', '#059669', '#0891b2'
  ]

  const colors = customColors.length > 0 ? customColors : defaultColors

  const exportData = (format) => {
    if (format === 'csv') {
      const csvContent = [
        Object.keys(data[0] || {}).join(','),
        ...data.map(row => Object.values(row).join(','))
      ].join('\n')
      
      const blob = new Blob([csvContent], { type: 'text/csv' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${exportFilename}.csv`
      a.click()
      window.URL.revokeObjectURL(url)
    } else if (format === 'json') {
      const jsonContent = JSON.stringify(data, null, 2)
      const blob = new Blob([jsonContent], { type: 'application/json' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${exportFilename}.json`
      a.click()
      window.URL.revokeObjectURL(url)
    }
  }

  const renderChart = () => {
    const commonProps = {
      data,
      margin: { top: 20, right: 30, left: 20, bottom: 5 },
      ...chartProps
    }

    const commonElements = (
      <>
        {showGrid && <CartesianGrid strokeDasharray="3 3" />}
        <XAxis 
          dataKey="name" 
          angle={-45} 
          textAnchor="end" 
          height={80}
          interval={0}
          tick={{ fontSize: 12 }}
        />
        <YAxis />
        <Tooltip 
          contentStyle={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)'
          }}
        />
        {showLegend && <Legend />}
      </>
    )

    switch (viewType) {
      case 'line':
        return (
          <LineChart {...commonProps}>
            {commonElements}
            {children || (
              <Line 
                type="monotone" 
                dataKey="value" 
                stroke={colors[0]} 
                strokeWidth={2}
                animationDuration={animationEnabled ? 300 : 0}
              />
            )}
          </LineChart>
        )

      case 'area':
        return (
          <AreaChart {...commonProps}>
            {commonElements}
            {children || (
              <Area 
                type="monotone" 
                dataKey="value" 
                fill={colors[0]} 
                fillOpacity={0.6}
                stroke={colors[0]}
                animationDuration={animationEnabled ? 300 : 0}
              />
            )}
          </AreaChart>
        )

      case 'pie':
        return (
          <PieChart {...commonProps}>
            {children || (
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                outerRadius={80}
                dataKey="value"
                animationDuration={animationEnabled ? 300 : 0}
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
                ))}
              </Pie>
            )}
            <Tooltip />
            {showLegend && <Legend />}
          </PieChart>
        )

      case 'bar':
      default:
        return (
          <BarChart {...commonProps}>
            {commonElements}
            {children || (
              <Bar 
                dataKey="value" 
                fill={colors[0]}
                animationDuration={animationEnabled ? 300 : 0}
              />
            )}
          </BarChart>
        )
    }
  }

  return (
    <Box>
      <SpaceBetween direction="vertical" size="m">
        {(title || showViewOptions || showExport) && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              {title && <Header variant="h3" description={description}>{title}</Header>}
            </div>
            
            <SpaceBetween direction="horizontal" size="s">
              {showViewOptions && (
                <div key="chart-options">
                  <Popover
                    header="Chart Options"
                    content={
                      <SpaceBetween direction="vertical" size="s">
                        <div key="toggle-grid">
                          <Toggle
                            checked={showGrid}
                            onChange={({ detail }) => setShowGrid(detail.checked)}
                          >
                            Show Grid
                          </Toggle>
                        </div>
                        <div key="toggle-legend">
                          <Toggle
                            checked={showLegend}
                            onChange={({ detail }) => setShowLegend(detail.checked)}
                          >
                            Show Legend
                          </Toggle>
                        </div>
                        <div key="toggle-animation">
                          <Toggle
                            checked={animationEnabled}
                            onChange={({ detail }) => setAnimationEnabled(detail.checked)}
                          >
                            Enable Animations
                          </Toggle>
                        </div>
                      </SpaceBetween>
                    }
                    size="medium"
                    position="bottom-left"
                    triggerType="custom"
                  >
                    <Button variant="icon" iconName="settings" />
                  </Popover>
                </div>
              )}

              <div key="chart-type">
                <ButtonDropdown
                  items={[
                    { id: 'bar', text: 'Bar Chart' },
                    { id: 'line', text: 'Line Chart' },
                    { id: 'area', text: 'Area Chart' },
                    { id: 'pie', text: 'Pie Chart' }
                  ]}
                  onItemClick={({ detail }) => setViewType(detail.id)}
                  variant="icon"
                  ariaLabel="Chart type"
                >
                  <Button variant="icon" iconName="view-full" />
                </ButtonDropdown>
              </div>

              {showExport && (
                <div key="export-options">
                  <ButtonDropdown
                    items={[
                      { id: 'csv', text: 'Export as CSV' },
                      { id: 'json', text: 'Export as JSON' }
                    ]}
                    onItemClick={({ detail }) => exportData(detail.id)}
                    variant="icon"
                    ariaLabel="Export options"
                  >
                    <Button variant="icon" iconName="download" />
                  </ButtonDropdown>
                </div>
              )}
            </SpaceBetween>
          </div>
        )}

        <div style={{ height: `${height}px` }}>
          <ResponsiveContainer width="100%" height="100%">
            {renderChart()}
          </ResponsiveContainer>
        </div>
      </SpaceBetween>
    </Box>
  )
}

export default InteractiveChart