// AWS Configuration
// Centralized configuration for AWS services
// Supports both runtime config (production) and build-time env vars (development)

let runtimeConfig = null

// Default configuration from build-time environment variables (development fallback)
const buildTimeConfig = {
  region: import.meta.env.VITE_AWS_REGION,

  cognito: {
    userPoolId: import.meta.env.VITE_USER_POOL_ID,
    userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID,
    identityPoolId: import.meta.env.VITE_IDENTITY_POOL_ID,
  },

  s3: {
    bucket: import.meta.env.VITE_S3_BUCKET,
  },

  dynamodb: {
    processingStatusTable: import.meta.env.VITE_DYNAMODB_TABLE_NAME,
    metricsTable: import.meta.env.VITE_DYNAMODB_METRICS_TABLE_NAME,
  },

  agentCore: {
    runtimeArn: import.meta.env.VITE_AGENTCORE_RUNTIME_ARN,
  },

  knowledgeBase: {
    id: import.meta.env.KNOWLEDGE_BASE_ID,
    dataSourceId: import.meta.env.KNOWLEDGE_BASE_DATA_SOURCE_ID,
    name: import.meta.env.KNOWLEDGE_BASE_NAME,
  },
}

// Load runtime configuration from CloudFront/S3
export const loadRuntimeConfig = async () => {
  if (runtimeConfig) {
    return runtimeConfig
  }

  try {
    // Try to fetch runtime config from deployed location
    const response = await fetch('/config.json')
    if (response.ok) {
      const config = await response.json()

      // Only use runtime config if it has valid data
      if (config.region && config.cognito?.userPoolId) {
        console.log('✅ Loaded runtime configuration from /config.json')
        runtimeConfig = config
        return runtimeConfig
      }
    }
  } catch (error) {
    console.warn('Runtime config not available, using build-time configuration')
  }

  // Fall back to build-time config for local development
  console.log('Using build-time environment variables')
  runtimeConfig = buildTimeConfig
  return runtimeConfig
}

// Export synchronous config accessor (will use cached runtime config or build-time config)
const awsConfig = runtimeConfig || buildTimeConfig

// Get current config (runtime or build-time)
export const getConfig = () => {
  return runtimeConfig || buildTimeConfig
}

// Validation helper
export const validateConfig = () => {
  const config = getConfig()
  const errors = []

  if (!config.region) errors.push('AWS region is not configured')
  if (!config.cognito.userPoolId) errors.push('Cognito User Pool ID is not configured')
  if (!config.cognito.userPoolClientId) errors.push('Cognito User Pool Client ID is not configured')
  if (!config.cognito.identityPoolId) errors.push('Cognito Identity Pool ID is not configured')
  if (!config.s3.bucket) errors.push('S3 bucket is not configured')
  if (!config.dynamodb.processingStatusTable) errors.push('DynamoDB processing status table is not configured')
  if (!config.dynamodb.metricsTable) errors.push('DynamoDB metrics table is not configured')

  return errors
}

// Get table names with validation
export const getTableNames = () => {
  const config = getConfig()
  const processingStatusTable = config.dynamodb.processingStatusTable
  const metricsTable = config.dynamodb.metricsTable

  if (!processingStatusTable) {
    console.error('DynamoDB processing status table is not configured')
  }

  if (!metricsTable) {
    console.error('DynamoDB metrics table is not configured')
  }

  return {
    processingStatusTable,
    metricsTable,
  }
}

export default awsConfig
