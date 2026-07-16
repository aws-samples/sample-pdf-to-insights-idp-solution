import React, { useState, useEffect } from 'react'
import ApiService from '../services/api'
import {
  Container,
  Header,
  Table,
  Button,
  StatusIndicator,
  SpaceBetween,
  Box,
  ColumnLayout,
  Badge
} from '@cloudscape-design/components'

function ProcessingStatus() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [lastRefresh, setLastRefresh] = useState(null)


  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'completed': return 'success'
      case 'processing': 
      case 'bda_processing': return 'in-progress'
      case 'failed': 
      case 'error': return 'error'
      default: return 'pending'
    }
  }

  const fetchProcessingStatus = async () => {
    setLoading(true)
    try {
      const processedDocs = await ApiService.getProcessingStatusData()
      setDocuments(processedDocs)
      setLastRefresh(new Date())
    } catch (error) {
      console.error('Error fetching processing status:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProcessingStatus()
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchProcessingStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const getStatusCounts = () => {
    const counts = {
      total: documents.length,
      processing: documents.filter(d => ['processing', 'bda_processing'].includes(d.status?.toLowerCase())).length,
      completed: documents.filter(d => d.status?.toLowerCase() === 'completed').length,
      failed: documents.filter(d => ['failed', 'error'].includes(d.status?.toLowerCase())).length
    }
    return counts
  }

  const statusCounts = getStatusCounts()

  return (
    <Container>
      <SpaceBetween direction="vertical" size="l">
        <Header 
          variant="h2"
          actions={
            <Button 
              onClick={fetchProcessingStatus} 
              loading={loading}
              iconName="refresh"
            >
              Refresh
            </Button>
          }
        >
          Document Processing Status
        </Header>

        {/* Status Overview Cards */}
        <ColumnLayout columns={4} variant="text-grid">
          <Box>
            <div style={{ textAlign: 'center' }}>
              <Box variant="h1" color="text-status-info">{statusCounts.total}</Box>
              <Box variant="small">Total Documents</Box>
            </div>
          </Box>
          <Box>
            <div style={{ textAlign: 'center' }}>
              <Box variant="h1" color="text-status-warning">{statusCounts.processing}</Box>
              <Box variant="small">Processing</Box>
            </div>
          </Box>
          <Box>
            <div style={{ textAlign: 'center' }}>
              <Box variant="h1" color="text-status-success">{statusCounts.completed}</Box>
              <Box variant="small">Completed</Box>
            </div>
          </Box>
          <Box>
            <div style={{ textAlign: 'center' }}>
              <Box variant="h1" color="text-status-error">{statusCounts.failed}</Box>
              <Box variant="small">Failed</Box>
            </div>
          </Box>
        </ColumnLayout>

        {/* Processing Status Table */}
        <Table
          columnDefinitions={[
            {
              id: 'docId',
              header: 'Document',
              cell: item => (
                <div>
                  <div style={{ fontWeight: 'bold' }}>
                    {item.docId.split('/').pop()}
                  </div>
                  <div style={{ fontSize: '12px', color: '#666' }}>
                    {item.docId}
                  </div>
                </div>
              ),
              sortingField: 'docId'
            },
            {
              id: 'status',
              header: 'Status',
              cell: item => (
                <StatusIndicator type={getStatusColor(item.status)}>
                  {item.status}
                </StatusIndicator>
              ),
              sortingField: 'status'
            },
            {
              id: 'uploadTime',
              header: 'Upload Time (UTC)',
              cell: item => new Date(item.uploadTime).toLocaleString(),
              sortingField: 'uploadTime'
            },
            {
              id: 'processingTime',
              header: 'Processing Time',
              cell: item => item.processingTime !== 'N/A' ? `${item.processingTime}s` : 'N/A',
              sortingField: 'processingTime'
            },
            {
              id: 'executionId',
              header: 'Execution',
              cell: item => (
                <div style={{ fontSize: '12px', fontFamily: 'monospace' }}>
                  {item.executionId !== 'N/A' ? item.executionId.split('-').pop() : 'N/A'}
                </div>
              )
            }
          ]}
          items={documents}
          loading={loading}
          loadingText="Loading processing status..."
          empty={
            <Box textAlign="center" color="inherit">
              <b>No documents found</b>
              <Box variant="p" color="inherit">
                Upload some PDF documents to see their processing status here.
              </Box>
            </Box>
          }
          sortingDisabled={false}
        />

        {lastRefresh && (
          <Box variant="small" color="text-status-inactive">
            Last updated: {lastRefresh.toLocaleTimeString()}
          </Box>
        )}
      </SpaceBetween>
    </Container>
  )
}

export default ProcessingStatus
