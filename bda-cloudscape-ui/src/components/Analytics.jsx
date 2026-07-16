import React, { useState, useEffect, useCallback } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import { DynamoDBClient, ScanCommand } from '@aws-sdk/client-dynamodb'
import awsConfig, { getTableNames } from '../config/aws-config'
import {
  Container,
  Header,
  Button,
  SpaceBetween,
  Box,
  ColumnLayout,
  Cards,
  Badge,
  ProgressBar,
  DateRangePicker,
  Select,
  Toggle,
  Alert,
  Icon,
  Grid
} from '@cloudscape-design/components'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart
} from 'recharts'
import { LoadingSkeleton, SkeletonCard, SkeletonChart, EnhancedStatusIndicator, InteractiveChart } from './shared'

function Analytics() {
  const [metrics, setMetrics] = useState([])
  const [statusData, setStatusData] = useState([])
  const [loading, setLoading] = useState(false)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(30)
  const [dateRange, setDateRange] = useState({
    type: 'relative',
    amount: 7,
    unit: 'day'
  })
  const [chartFilters, setChartFilters] = useState({
    showCompleted: true,
    showProcessing: true,
    showFailed: true
  })
  const [error, setError] = useState('')

  const fetchAnalyticsData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const session = await fetchAuthSession()
      const credentials = session.credentials

      const dynamoClient = new DynamoDBClient({
        region: awsConfig.region,
        credentials: {
          accessKeyId: credentials.accessKeyId,
          secretAccessKey: credentials.secretAccessKey,
          sessionToken: credentials.sessionToken
        }
      })

      const { processingStatusTable, metricsTable } = getTableNames()

      // Validate table names exist
      if (!metricsTable || !processingStatusTable) {
        throw new Error('DynamoDB table names are not configured. Please check your environment variables.')
      }

      // Fetch processing metrics
      const metricsCommand = new ScanCommand({
        TableName: metricsTable,
        Limit: 100
      })

      // Fetch processing status
      const statusCommand = new ScanCommand({
        TableName: processingStatusTable,
        Limit: 100
      })

      const [metricsResult, statusResult] = await Promise.all([
        dynamoClient.send(metricsCommand),
        dynamoClient.send(statusCommand)
      ])

      // Process metrics data
      const processedMetrics = metricsResult.Items?.map(item => ({
        executionId: item.execution_id?.S || 'Unknown',
        timestamp: item.timestamp?.S || 'Unknown',
        totalTime: parseFloat(item.total_processing_time?.N || '0'),
        bdaTime: parseFloat(item.bda_processing_time?.N || '0'),
        postProcessingTime: parseFloat(item.post_processing_time?.N || '0'),
        documentCount: parseInt(item.document_count?.N || '0'),
        status: item.status?.S || 'Unknown'
      })) || []

      // Process status data
      const processedStatus = statusResult.Items?.map(item => ({
        docId: item.doc_id?.S || 'Unknown',
        status: item.status?.S || 'Unknown',
        startTime: item.start_time?.S || item.initialization_time?.S || 'Unknown',
        completedTime: item.completed_time?.S || null,
        pageCount: parseInt(item.page_count?.N || '0'),
        processingTime: calculateProcessingTime(item)
      })) || []

      setMetrics(processedMetrics)
      setStatusData(processedStatus)
      setLastRefresh(new Date())
    } catch (error) {
      console.error('Error fetching analytics data:', error)
      setError('Failed to fetch analytics data. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [])

  const calculateProcessingTime = (item) => {
    try {
      const startTime = item.start_time?.S || item.initialization_time?.S
      const endTime = item.completed_time?.S || item.bda_completion_time?.S
      
      if (startTime && endTime) {
        const start = new Date(startTime)
        const end = new Date(endTime)
        return Math.round((end - start) / 1000)
      }
    } catch (error) {
      console.log('Error calculating processing time:', error)
    }
    return 0
  }

  useEffect(() => {
    fetchAnalyticsData()
  }, [])

  // Auto-refresh functionality
  useEffect(() => {
    if (!autoRefresh) return
    
    const interval = setInterval(() => {
      fetchAnalyticsData()
    }, refreshInterval * 1000)
    
    return () => clearInterval(interval)
  }, [autoRefresh, refreshInterval, fetchAnalyticsData])

  // Calculate KPIs with trend data
  const totalDocuments = statusData.length
  const completedDocuments = statusData.filter(d => d.status === 'COMPLETED').length
  const processingDocuments = statusData.filter(d => d.status === 'PROCESSING' || d.status === 'BDA_PROCESSING').length
  const failedDocuments = statusData.filter(d => d.status === 'FAILED' || d.status === 'ERROR').length
  const successRate = totalDocuments > 0 ? Math.round((completedDocuments / totalDocuments) * 100) : 0
  const avgProcessingTime = statusData.length > 0 ? 
    Math.round(statusData.reduce((sum, d) => sum + d.processingTime, 0) / statusData.length) : 0
  
  // Calculate trends (mock data for demo - would come from historical data)
  const trends = {
    totalDocuments: { value: totalDocuments, change: +12, trend: 'up' },
    successRate: { value: successRate, change: +5, trend: 'up' },
    avgProcessingTime: { value: avgProcessingTime, change: -8, trend: 'down' },
    totalPages: { 
      value: statusData.reduce((sum, d) => sum + d.pageCount, 0), 
      change: +15, 
      trend: 'up' 
    }
  }

  // Prepare chart data with filtering
  const getFilteredStatusData = () => {
    const data = []
    if (chartFilters.showCompleted) data.push({ name: 'Completed', value: completedDocuments, color: '#16a34a' })
    if (chartFilters.showProcessing) data.push({ name: 'Processing', value: processingDocuments, color: '#f59e0b' })
    if (chartFilters.showFailed) data.push({ name: 'Failed', value: failedDocuments, color: '#dc2626' })
    return data
  }
  
  const statusChartData = getFilteredStatusData()

  const processingTimeData = statusData
    .filter(d => d.processingTime > 0)
    .slice(-10)
    .map((d, index) => {
      // Extract meaningful part of filename
      const fileName = d.docId.split('/').pop().replace(/\.(pdf|docx?|txt)$/i, '');
      
      // Create a more readable minified name by extracting key parts
      let displayName = fileName;
      
      // Try to extract meaningful business document names
      if (fileName.includes('CoStar') || fileName.includes('Retail') || fileName.includes('Report')) {
        // Extract the meaningful part after the ID
        const match = fileName.match(/\d+-(.+)/);
        if (match) {
          displayName = match[1];
        }
      }
      
      // If still too long, intelligently truncate
      if (displayName.length > 25) {
        const parts = displayName.split(/[-_\s]/);
        if (parts.length > 2) {
          // Take first 2 and last part
          displayName = parts[0] + '...' + parts[parts.length - 1];
        } else if (parts.length === 2) {
          // Take first part and truncate second
          displayName = parts[0] + '...' + parts[1].slice(-8);
        } else {
          // Single word - truncate from middle
          const mid = Math.floor(displayName.length / 2);
          displayName = displayName.slice(0, 12) + '...' + displayName.slice(-8);
        }
      }
      
      return {
        name: displayName,  // Minified name for display
        fullName: fileName,  // Keep full name for tooltip
        time: d.processingTime,
        pages: d.pageCount
      };
    })

  const dailyVolumeData = statusData
    .reduce((acc, doc) => {
      if (doc.startTime && doc.startTime !== 'Unknown') {
        const date = new Date(doc.startTime).toLocaleDateString()
        acc[date] = (acc[date] || 0) + 1
      }
      return acc
    }, {})

  const volumeChartData = Object.entries(dailyVolumeData)
    .slice(-7)
    .map(([date, count]) => ({ date, documents: count }))

  const renderKPICard = (title, value, change, trend, unit = '', description = '') => (
    <div style={{
      background: '#ffffff',
      border: '1px solid #e2e8f0',
      borderRadius: '8px',
      padding: '20px',
      transition: 'all 0.2s ease'
    }}>
      <div style={{ marginBottom: '12px' }}>
        <div style={{
          fontSize: '32px',
          fontWeight: '600',
          color: '#0a0e27',
          marginBottom: '4px'
        }}>
          {value}{unit}
        </div>
        <div style={{
          fontSize: '14px',
          fontWeight: '500',
          color: '#64748b'
        }}>
          {title}
        </div>
      </div>
      {change !== undefined && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}>
          <Icon
            name={trend === 'up' ? 'angle-up' : 'angle-down'}
            variant={trend === 'up' ? 'success' : trend === 'down' ? 'error' : 'normal'}
          />
          <span style={{
            fontSize: '13px',
            fontWeight: '500',
            color: trend === 'up' ? '#10b981' : trend === 'down' ? '#ef4444' : '#64748b'
          }}>
            {Math.abs(change)}%
          </span>
        </div>
      )}
      {description && (
        <div style={{
          fontSize: '12px',
          color: '#94a3b8',
          marginTop: '4px'
        }}>
          {description}
        </div>
      )}
    </div>
  )

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '24px' }}>
      <SpaceBetween direction="vertical" size="l">
        {/* Header with Actions */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '8px'
        }}>
          <div>
            <h1 style={{
              fontSize: '28px',
              fontWeight: '600',
              color: '#0a0e27',
              margin: '0 0 8px 0',
              letterSpacing: '-0.02em'
            }}>
              Analytics Dashboard
            </h1>
            <p style={{
              fontSize: '14px',
              color: '#64748b',
              margin: 0
            }}>
              Real-time insights into document processing performance
            </p>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <Select
              selectedOption={{ label: `${refreshInterval}s`, value: refreshInterval }}
              onChange={({ detail }) => setRefreshInterval(detail.selectedOption.value)}
              options={[
                { label: '10s', value: 10 },
                { label: '30s', value: 30 },
                { label: '60s', value: 60 },
                { label: '5m', value: 300 }
              ]}
              disabled={!autoRefresh}
            />
            <Toggle
              checked={autoRefresh}
              onChange={({ detail }) => setAutoRefresh(detail.checked)}
            >
              Auto-refresh
            </Toggle>
            <Button
              onClick={fetchAnalyticsData}
              loading={loading}
              iconName="refresh"
              variant="primary"
            >
              Refresh
            </Button>
          </div>
        </div>

        {error && (
          <Alert type="error" dismissible onDismiss={() => setError('')}>
            {error}
          </Alert>
        )}

        {/* Enhanced KPI Cards */}
        <Grid gridDefinition={[
          { colspan: { default: 12, xs: 6, s: 3 } },
          { colspan: { default: 12, xs: 6, s: 3 } },
          { colspan: { default: 12, xs: 6, s: 3 } },
          { colspan: { default: 12, xs: 6, s: 3 } }
        ]} variant="text-grid">
          {renderKPICard(
            'Total Documents', 
            trends.totalDocuments.value, 
            trends.totalDocuments.change, 
            trends.totalDocuments.trend,
            '',
            'Documents processed'
          )}
          {renderKPICard(
            'Success Rate', 
            trends.successRate.value, 
            trends.successRate.change, 
            trends.successRate.trend,
            '%',
            'Completion percentage'
          )}
          {renderKPICard(
            'Avg Processing Time', 
            trends.avgProcessingTime.value, 
            trends.avgProcessingTime.change, 
            trends.avgProcessingTime.trend,
            's',
            'Time per document'
          )}
          {renderKPICard(
            'Total Pages', 
            trends.totalPages.value, 
            trends.totalPages.change, 
            trends.totalPages.trend,
            '',
            'Pages processed'
          )}
        </Grid>

        {/* Chart Filters */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          padding: '12px 16px',
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: '8px'
        }}>
          <div style={{
            fontSize: '14px',
            fontWeight: '600',
            color: '#0a0e27'
          }}>
            Chart Filters:
          </div>
          <Toggle
            checked={chartFilters.showCompleted}
            onChange={({ detail }) => setChartFilters(prev => ({ ...prev, showCompleted: detail.checked }))}
          >
            Completed
          </Toggle>
          <Toggle
            checked={chartFilters.showProcessing}
            onChange={({ detail }) => setChartFilters(prev => ({ ...prev, showProcessing: detail.checked }))}
          >
            Processing
          </Toggle>
          <Toggle
            checked={chartFilters.showFailed}
            onChange={({ detail }) => setChartFilters(prev => ({ ...prev, showFailed: detail.checked }))}
          >
            Failed
          </Toggle>
        </div>

        {/* Enhanced Charts */}
        <Grid gridDefinition={[
          { colspan: { default: 12, l: 6 } },
          { colspan: { default: 12, l: 6 } }
        ]} variant="text-grid">
          <div style={{
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '20px'
          }}>
            <div style={{ marginBottom: '16px' }}>
              <h3 style={{
                fontSize: '16px',
                fontWeight: '600',
                color: '#0a0e27',
                margin: '0 0 4px 0'
              }}>
                Document Status Distribution
              </h3>
              <p style={{
                fontSize: '13px',
                color: '#64748b',
                margin: 0
              }}>
                Current status breakdown of all documents
              </p>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={statusChartData}
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  dataKey="value"
                  animationDuration={300}
                >
                  {statusChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div style={{
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '20px'
          }}>
            <div style={{ marginBottom: '16px' }}>
              <h3 style={{
                fontSize: '16px',
                fontWeight: '600',
                color: '#0a0e27',
                margin: '0 0 4px 0'
              }}>
                Daily Document Volume
              </h3>
              <p style={{
                fontSize: '13px',
                color: '#64748b',
                margin: 0
              }}>
                Document processing volume over time
              </p>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={volumeChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 12 }} stroke="#94a3b8" />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="documents"
                  fill="#3b82f6"
                  fillOpacity={0.6}
                  stroke="#3b82f6"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Grid>

        {/* Processing Times - Full Width with Enhanced Chart */}
        <div style={{
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          padding: '20px'
        }}>
          <div style={{ marginBottom: '16px' }}>
            <h3 style={{
              fontSize: '16px',
              fontWeight: '600',
              color: '#0a0e27',
              margin: '0 0 4px 0'
            }}>
              Processing Times & Page Counts
            </h3>
            <p style={{
              fontSize: '13px',
              color: '#64748b',
              margin: 0
            }}>
              Performance metrics for recent documents
            </p>
          </div>
          <div style={{ height: '400px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={processingTimeData}
                margin={{ top: 20, right: 40, left: 40, bottom: 100 }}
                barCategoryGap="25%"
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="name"
                  angle={-45}
                  textAnchor="end"
                  height={100}
                  interval={0}
                  tick={{ fontSize: 12, fill: '#64748b' }}
                />
                <YAxis
                  yAxisId="left"
                  orientation="left"
                  stroke="#964B00"
                  label={{ value: 'Time (s)', angle: -90, position: 'insideLeft' }}
                  domain={[0, 'dataMax + 10']}
                  tick={{ fontSize: 12, fill: '#64748b' }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#3b82f6"
                  label={{ value: 'Pages', angle: 90, position: 'insideRight' }}
                  domain={[0, 100]}
                  tick={{ fontSize: 12, fill: '#64748b' }}
                />
                <Tooltip
                  formatter={(value, name) => {
                    if (name === 'Processing Time (s)') return [`${value}s`, 'Processing Time'];
                    if (name === 'Page Count') return [value, 'Page Count'];
                    return [value, name];
                  }}
                  labelFormatter={(label, payload) => {
                    if (payload && payload[0]) {
                      return payload[0].payload.fullName || label;
                    }
                    return label;
                  }}
                />
                <Legend />
                <Bar yAxisId="left" dataKey="time" fill="#964B00" name="Processing Time (s)" />
                <Bar yAxisId="right" dataKey="pages" fill="#3b82f6" name="Page Count" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Enhanced Recent Activity */}
        <div style={{
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          padding: '20px'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '16px'
          }}>
            <div>
              <h3 style={{
                fontSize: '16px',
                fontWeight: '600',
                color: '#0a0e27',
                margin: '0 0 4px 0'
              }}>
                Recent Processing Activity
              </h3>
              <p style={{
                fontSize: '13px',
                color: '#64748b',
                margin: 0
              }}>
                Latest document processing activity with status updates
              </p>
            </div>
            <button style={{
              padding: '6px 12px',
              background: '#64748b',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: '500',
              cursor: 'pointer'
            }}>
              Manual Refresh
            </button>
          </div>

          {statusData.length === 0 ? (
            <div style={{
              textAlign: 'center',
              padding: '48px 24px',
              color: '#94a3b8'
            }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📁</div>
              <h4 style={{
                fontSize: '16px',
                fontWeight: '600',
                color: '#0a0e27',
                margin: '0 0 8px 0'
              }}>
                No recent uploads
              </h4>
              <p style={{
                fontSize: '14px',
                color: '#64748b',
                margin: 0
              }}>
                Upload your first document to get started with AI-powered analysis
              </p>
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '16px'
            }}>
              {statusData.slice(0, 6).map((item, index) => (
                <div key={index} style={{
                  background: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '6px',
                  padding: '16px'
                }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: '12px'
                  }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      flex: 1,
                      minWidth: 0
                    }}>
                      <Icon name="file" />
                      <span style={{
                        fontSize: '14px',
                        fontWeight: '600',
                        color: '#0a0e27',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                      }}>
                        {item.docId.split('/').pop().substring(0, 30)}
                      </span>
                    </div>
                    <Badge color={
                      item.status === 'COMPLETED' ? 'green' :
                      item.status === 'PROCESSING' || item.status === 'BDA_PROCESSING' ? 'blue' :
                      'red'
                    }>
                      {item.status === 'COMPLETED' ? 'Completed' :
                       item.status === 'PROCESSING' || item.status === 'BDA_PROCESSING' ? 'Processing' :
                       'Failed'}
                    </Badge>
                  </div>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '8px',
                    marginBottom: '8px'
                  }}>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>
                      <strong>Pages:</strong> {item.pageCount}
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b' }}>
                      <strong>Time:</strong> {item.processingTime}s
                    </div>
                  </div>
                  <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                    <strong>Started:</strong> {new Date(item.startTime).toLocaleString()}
                  </div>
                  {(item.status === 'PROCESSING' || item.status === 'BDA_PROCESSING') && (
                    <div style={{ marginTop: '12px' }}>
                      <ProgressBar
                        value={22}
                        additionalInfo="Processing..."
                        status="in-progress"
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {lastRefresh && (
          <div style={{
            fontSize: '12px',
            color: '#94a3b8',
            textAlign: 'center'
          }}>
            Last updated: {lastRefresh.toLocaleTimeString()}
          </div>
        )}
      </SpaceBetween>
    </div>
  )
}

export default Analytics
