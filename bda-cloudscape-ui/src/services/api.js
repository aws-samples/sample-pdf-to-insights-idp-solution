import { fetchAuthSession } from 'aws-amplify/auth'
import { DynamoDBClient, ScanCommand } from '@aws-sdk/client-dynamodb'
import awsConfig, { getTableNames } from '../config/aws-config'

class ApiService {
  constructor() {
    this.dynamoClient = null
  }

  async initializeClient() {
    if (this.dynamoClient) return this.dynamoClient

    console.log('Fetching auth session...')
    const session = await fetchAuthSession({ forceRefresh: true })
    console.log('Session:', session)
    console.log('Credentials:', session.credentials)
    
    const credentials = session.credentials

    if (!credentials || !credentials.accessKeyId) {
      console.error('No credentials found')
      throw new Error('Unable to get identity credentials')
    }

    this.dynamoClient = new DynamoDBClient({
      region: awsConfig.region,
      credentials: {
        accessKeyId: credentials.accessKeyId,
        secretAccessKey: credentials.secretAccessKey,
        sessionToken: credentials.sessionToken
      }
    })

    return this.dynamoClient
  }

  async getProcessingStatusData() {
    try {
      // Check if user is authenticated first
      const session = await fetchAuthSession({ forceRefresh: true })
      if (!session.credentials || !session.credentials.accessKeyId) {
        console.log('User not authenticated, skipping API call')
        return []
      }
      
      const client = await this.initializeClient()
      const { processingStatusTable } = getTableNames()

      if (!processingStatusTable) {
        console.error('VITE_DYNAMODB_TABLE_NAME is not configured')
        return []
      }

      const command = new ScanCommand({
        TableName: processingStatusTable,
        Limit: 100
      })

      const result = await client.send(command)
      
      const processedDocs = result.Items?.map(item => {
        const timestamp = item.initialization_time?.S || 
                         item.start_time?.S || 
                         item.timestamp?.S

        const docName = (item.doc_id?.S || 'Unknown').split('/').pop() || 'Unknown'
        const uniqueId = timestamp ? 
          `${docName.substring(0, 8)}-${new Date(timestamp).getTime().toString().slice(-6)}` : 
          docName.substring(0, 12)

        return {
          docId: item.doc_id?.S || 'Unknown',
          status: item.status?.S || 'Unknown',
          uploadTime: timestamp || 'Unknown',
          completedTime: item.bda_completion_time?.S || item.completed_time?.S || null,
          executionId: uniqueId,
          stepFunctionArn: item.step_function_arn?.S || item.execution_arn?.S || 'N/A',
          processingTime: item.processing_time_seconds?.N || this.calculateProcessingTime(item),
          errorMessage: item.error_message?.S || null,
          pageCount: item.page_count?.N || 'N/A',
          outputLocation: item.output_location?.S || null,
          textExtractionResult: item.text_extraction_result?.S || null,
          markdownExtractionResult: item.markdown_extraction_result?.S || null,
          bucket: item.bucket?.S || null,
          docType: item.doc_type?.S || null
        }
      }) || []

      processedDocs.sort((a, b) => {
        const timeA = new Date(a.uploadTime)
        const timeB = new Date(b.uploadTime)
        if (timeA.getTime() === timeB.getTime()) {
          return a.docId.localeCompare(b.docId)
        }
        return timeB - timeA
      })

      return processedDocs
    } catch (error) {
      console.error('Error fetching processing status:', error)
      return []
    }
  }

  calculateProcessingTime(item) {
    try {
      const startTime = item.start_time?.S || item.initialization_time?.S
      const endTime = item.completed_time?.S || item.bda_completion_time?.S
      
      if (startTime && endTime) {
        const start = new Date(startTime)
        const end = new Date(endTime)
        const diffSeconds = Math.round((end - start) / 1000)
        return diffSeconds.toString()
      }
    } catch (error) {
      console.log('Error calculating processing time:', error)
    }
    return 'N/A'
  }

  async getDashboardMetrics() {
    try {
      const documents = await this.getProcessingStatusData()
      
      const totalDocs = documents.length
      const completedDocs = documents.filter(d => d.status?.toUpperCase() === 'COMPLETED').length
      const processingDocs = documents.filter(d => ['PROCESSING', 'BDA_PROCESSING', 'IN_PROGRESS'].includes(d.status?.toUpperCase())).length
      const failedDocs = documents.filter(d => ['FAILED', 'ERROR'].includes(d.status?.toUpperCase())).length
      
      // Calculate percentage change (mock for now - in real app would compare with previous period)
      const completionRate = totalDocs > 0 ? Math.round((completedDocs / totalDocs) * 100) : 0

      return [
        { 
          label: 'Documents Processed', 
          value: completedDocs.toString(), 
          change: totalDocs > 0 ? `${completionRate}%` : '0%', 
          positive: completionRate > 0 
        },
        { 
          label: 'Active Analyses', 
          value: processingDocs.toString(), 
          change: processingDocs > 0 ? 'In Progress' : 'Idle', 
          neutral: true 
        }
      ]
    } catch (error) {
      console.error('Error fetching dashboard metrics:', error)
      // Return default values for fresh deployment
      return [
        { label: 'Documents Processed', value: '0', change: '0%', neutral: true },
        { label: 'Active Analyses', value: '0', change: 'Idle', neutral: true }
      ]
    }
  }

  async getQuickStats() {
    try {
      const documents = await this.getProcessingStatusData()
      const processingDocs = documents.filter(d => ['PROCESSING', 'BDA_PROCESSING', 'IN_PROGRESS'].includes(d.status?.toUpperCase())).length
      
      return {
        activeProcessing: processingDocs,
        totalDocuments: documents.length,
        serverStatus: 'Online'
      }
    } catch (error) {
      console.error('Error fetching quick stats:', error)
      return {
        activeProcessing: 0,
        totalDocuments: 0,
        serverStatus: 'Online'
      }
    }
  }

  getDeploymentId() {
    // Generate a deployment ID based on environment variables or app version
    const region = import.meta.env.VITE_AWS_REGION || 'unknown'
    const environment = import.meta.env.VITE_ENVIRONMENT || 'dev'
    const timestamp = import.meta.env.VITE_BUILD_TIMESTAMP || Date.now().toString()
    
    return `${environment}-${region}-${timestamp.slice(-8)}`
  }

  async getRecentUploads() {
    try {
      const deploymentId = this.getDeploymentId()
      const uploads = JSON.parse(localStorage.getItem(`uploads_${deploymentId}`) || '[]')
      
      // Sort by upload time, most recent first
      return uploads
        .sort((a, b) => new Date(b.uploadTime) - new Date(a.uploadTime))
        .slice(0, 5) // Limit to 5 most recent
        .map(upload => ({
          ...upload,
          uploadTime: this.formatRelativeTime(upload.uploadTime)
        }))
    } catch (error) {
      console.error('Error getting recent uploads:', error)
      return []
    }
  }

  async storeUploadMetadata(uploads) {
    try {
      const deploymentId = this.getDeploymentId()
      const existingUploads = JSON.parse(localStorage.getItem(`uploads_${deploymentId}`) || '[]')
      
      const newUploads = uploads.map(upload => ({
        name: upload.file,
        key: upload.key,
        uploadTime: new Date().toISOString(),
        status: 'completed',
        size: this.formatFileSize(upload.fileSize || 0),
        deploymentId
      }))
      
      const allUploads = [...newUploads, ...existingUploads].slice(0, 20) // Keep last 20
      localStorage.setItem(`uploads_${deploymentId}`, JSON.stringify(allUploads))
      
      return true
    } catch (error) {
      console.error('Error storing upload metadata:', error)
      return false
    }
  }

  formatRelativeTime(dateString) {
    try {
      const date = new Date(dateString)
      const now = new Date()
      const diffInSeconds = Math.floor((now - date) / 1000)
      
      if (diffInSeconds < 60) return 'Just now'
      if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`
      if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`
      if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`
      
      return date.toLocaleDateString()
    } catch (error) {
      return 'Unknown'
    }
  }

  formatFileSize(bytes) {
    if (!bytes || bytes === 0) return 'Unknown'
    
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    
    if (i === 0) return `${bytes} ${sizes[i]}`
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
  }
}

export default new ApiService()