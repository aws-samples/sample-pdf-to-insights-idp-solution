import React, { useState, useCallback, useRef, useEffect } from 'react'
import { uploadData } from 'aws-amplify/storage'
import { fetchAuthSession } from 'aws-amplify/auth'
import apiService from '../services/api'
import {
  Container,
  Header,
  FileUpload,
  Button,
  SpaceBetween,
  FormField,
  Checkbox,
  Input,
  Alert,
  ProgressBar,
  Box,
  Badge,
  Cards,
  Grid,
  Icon,
  StatusIndicator,
  Spinner,
  Popover,
  Toggle
} from '@cloudscape-design/components'

function DocumentUpload() {
  const [files, setFiles] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState({})
  const [uploadResults, setUploadResults] = useState([])
  const [recentUploads, setRecentUploads] = useState([])
  const [loadingRecentUploads, setLoadingRecentUploads] = useState(false)
  const [options, setOptions] = useState({
    extractText: true,
    extractMarkdown: true,
    syncToKB: true
  })
  const [error, setError] = useState('')
  const [dragActive, setDragActive] = useState(false)
  const [fileValidationErrors, setFileValidationErrors] = useState({})
  const [estimatedTime, setEstimatedTime] = useState(0)
  const fileInputRef = useRef(null)

  // Load recent uploads on component mount
  useEffect(() => {
    loadRecentUploads()
  }, [])

  const loadRecentUploads = async () => {
    setLoadingRecentUploads(true)
    try {
      const uploads = await apiService.getRecentUploads()
      setRecentUploads(uploads)
    } catch (error) {
      console.error('Error loading recent uploads:', error)
      // Keep empty array as fallback for fresh deployments
    } finally {
      setLoadingRecentUploads(false)
    }
  }

  const validateFile = (file) => {
    const errors = []
    if (file.size > 25 * 1024 * 1024) {
      errors.push('File size exceeds 25MB limit')
    }
    if (!file.type === 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      errors.push('Only PDF files are supported')
    }
    return errors
  }

  const calculateEstimatedTime = (fileList) => {
    const totalSize = fileList.reduce((sum, file) => sum + file.size, 0)
    const estimatedSeconds = Math.ceil((totalSize / (1024 * 1024)) * 2) // 2 seconds per MB
    setEstimatedTime(estimatedSeconds)
  }

  const handleFileChange = ({ detail }) => {
    const newFiles = detail.value
    const validationErrors = {}
    
    newFiles.forEach(file => {
      const errors = validateFile(file)
      if (errors.length > 0) {
        validationErrors[file.name] = errors
      }
    })
    
    setFiles(newFiles)
    setFileValidationErrors(validationErrors)
    calculateEstimatedTime(newFiles)
    setError('')
  }

  const handleOptionChange = (option, value) => {
    setOptions(prev => ({ ...prev, [option]: value }))
  }

  const uploadFile = async (file) => {
    try {
      // CRITICAL: Fetch credentials before upload
      console.log('Checking authentication before upload...')
      const session = await fetchAuthSession({ forceRefresh: false })
      console.log('Session state:', {
        hasCredentials: !!session.credentials,
        hasTokens: !!session.tokens,
        hasIdentityId: !!session.identityId
      })

      if (!session.credentials || !session.identityId) {
        throw new Error('Not authenticated. Please sign out and sign back in.')
      }

      // Use Identity ID for the path (required by IAM policy)
      const identityId = session.identityId
      const timestamp = Date.now()
      const key = `uploads/${identityId}/${timestamp}-${file.name}`

      console.log('Uploading to S3 with key:', key)
      console.log('Identity ID:', identityId)

      const result = await uploadData({
        path: key,  // Use 'path' in v6 to avoid automatic /public/ prefix
        data: file,
        options: {
          onProgress: ({ transferredBytes, totalBytes }) => {
            const progress = Math.round((transferredBytes / totalBytes) * 100)
            setUploadProgress(prev => ({ ...prev, [file.name]: progress }))
          },
          metadata: {
            identityId,
            uploadTime: new Date().toISOString(),
            fileSize: file.size.toString(),
            originalName: file.name
          }
        }
      }).result

      console.log('Upload successful for:', file.name)
      return { file: file.name, key, success: true, result, identityId, timestamp, fileSize: file.size }
    } catch (err) {
      console.error('Upload error:', err)
      return { file: file.name, success: false, error: err.message }
    }
  }

  const handleDrag = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleDragIn = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(true)
  }, [])

  const handleDragOut = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    
    const droppedFiles = Array.from(e.dataTransfer.files)
    const pdfFiles = droppedFiles.filter(file => 
      file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    )
    
    setFiles(prev => [...prev, ...pdfFiles])
    calculateEstimatedTime([...files, ...pdfFiles])
  }, [files])

  const removeFile = (indexToRemove) => {
    const newFiles = files.filter((_, index) => index !== indexToRemove)
    setFiles(newFiles)
    calculateEstimatedTime(newFiles)
  }

  const clearAllFiles = () => {
    setFiles([])
    setFileValidationErrors({})
    setEstimatedTime(0)
  }

  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select at least one PDF file')
      return
    }

    const hasErrors = Object.keys(fileValidationErrors).length > 0
    if (hasErrors) {
      setError('Please fix file validation errors before uploading')
      return
    }

    setUploading(true)
    setUploadResults([])
    setUploadProgress({})
    setError('')

    try {
      const results = await Promise.all(files.map(uploadFile))
      setUploadResults(results)
      
      // Add successful uploads to recent uploads and store metadata
      const successfulUploads = results.filter(r => r.success)
      if (successfulUploads.length > 0) {
        // Store upload metadata for this deployment
        await apiService.storeUploadMetadata(successfulUploads)
        
        // Refresh recent uploads from API
        await loadRecentUploads()
        
        setFiles([])
        setEstimatedTime(0)
      }
    } catch (err) {
      setError('Upload failed: ' + err.message)
    } finally {
      setUploading(false)
    }
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatTime = (seconds) => {
    if (seconds < 60) return `${seconds}s`
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  }

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', padding: '24px 24px' }}>
      <SpaceBetween direction="vertical" size="l">
        {/* Header Section - Dropbox Style */}
        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
          <h1 style={{
            fontSize: '32px',
            fontWeight: '600',
            color: '#0a0e27',
            margin: '0 0 12px 0',
            letterSpacing: '-0.02em'
          }}>
            Upload your documents
          </h1>
          <p style={{
            fontSize: '16px',
            color: '#637381',
            margin: 0,
            fontWeight: '400'
          }}>
            Share PDFs for AI-powered analysis and insights
          </p>
        </div>
        
        {error && (
          <Alert type="error" dismissible onDismiss={() => setError('')}>
            {error}
          </Alert>
        )}

        {/* Dropbox-Style Upload Zone */}
        <div
          className={`upload-zone ${dragActive ? 'drag-active' : ''}`}
          onDragEnter={handleDragIn}
          onDragLeave={handleDragOut}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          style={{
            border: dragActive ? '3px dashed #0a0e27' : '2px dashed #c7cdd1',
            borderRadius: '16px',
            padding: '36px 24px',
            backgroundColor: dragActive ? '#eff6ff' : '#fafbfc',
            transition: 'all 0.2s ease',
            textAlign: 'center',
            cursor: 'pointer',
            position: 'relative'
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
            {/* Large Icon */}
            <div style={{
              width: '56px',
              height: '56px',
              background: dragActive ? '#0a0e27' : '#f7f9fa',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s ease',
              boxShadow: dragActive ? '0 8px 16px rgba(10, 14, 39, 0.2)' : 'none'
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={dragActive ? '#ffffff' : '#0a0e27'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
            </div>

            {/* Text */}
            <div>
              <div style={{
                fontSize: '20px',
                fontWeight: '500',
                color: '#0a0e27',
                marginBottom: '8px',
                letterSpacing: '-0.01em'
              }}>
                {dragActive ? 'Drop to upload' : 'Drag and drop files here'}
              </div>
              <div style={{
                fontSize: '15px',
                color: '#637381',
                marginBottom: '20px'
              }}>
                or click to browse
              </div>
              <div style={{
                fontSize: '13px',
                color: '#99a4ae',
                fontWeight: '400'
              }}>
                PDF files • Up to 25 MB each
              </div>
            </div>

            {/* CTA Button */}
            {!dragActive && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  fileInputRef.current?.click()
                }}
                style={{
                  padding: '10px 20px',
                  background: '#0a0e27',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  marginTop: '4px'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#05070f'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#0a0e27'}
              >
                Choose files
              </button>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,application/pdf"
            onChange={(e) => {
              const fileList = Array.from(e.target.files || [])
              handleFileChange({ detail: { value: fileList } })
            }}
            style={{ display: 'none' }}
          />
        </div>

        {/* File List - Dropbox Style */}
        {files.length > 0 && (
          <div style={{ marginTop: '20px' }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '16px'
            }}>
              <div style={{
                fontSize: '14px',
                color: '#637381',
                fontWeight: '400'
              }}>
                {files.length} {files.length === 1 ? 'file' : 'files'} • {formatFileSize(files.reduce((sum, f) => sum + f.size, 0))}
              </div>
              <button
                onClick={clearAllFiles}
                disabled={uploading}
                style={{
                  padding: '8px 12px',
                  background: 'transparent',
                  color: '#0061ff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: uploading ? 'not-allowed' : 'pointer',
                  transition: 'all 0.15s ease',
                  opacity: uploading ? 0.5 : 1
                }}
                onMouseEnter={(e) => !uploading && (e.currentTarget.style.background = '#f0f6ff')}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                Clear all
              </button>
            </div>

            {/* File List */}
            <div style={{
              background: '#ffffff',
              border: '1px solid #e1e4e8',
              borderRadius: '12px',
              overflow: 'hidden'
            }}>
              {files.map((file, index) => {
                const hasError = fileValidationErrors[file.name]
                const progress = uploadProgress[file.name]

                return (
                  <div
                    key={index}
                    style={{
                      padding: '16px 20px',
                      borderBottom: index < files.length - 1 ? '1px solid #f0f2f4' : 'none',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '14px',
                      background: hasError ? '#fff5f5' : '#ffffff',
                      transition: 'background 0.15s ease',
                      position: 'relative',
                      overflow: 'hidden'
                    }}
                    onMouseEnter={(e) => !hasError && (e.currentTarget.style.background = '#fafbfc')}
                    onMouseLeave={(e) => !hasError && (e.currentTarget.style.background = '#ffffff')}
                  >
                    {/* Progress Indicator */}
                    {progress !== undefined && (
                      <div style={{
                        position: 'absolute',
                        bottom: 0,
                        left: 0,
                        height: '2px',
                        width: `${progress}%`,
                        background: '#0061ff',
                        transition: 'width 0.3s ease'
                      }} />
                    )}

                    {/* PDF Icon */}
                    <div style={{
                      width: '40px',
                      height: '40px',
                      background: hasError ? '#fde8e8' : '#f0f6ff',
                      borderRadius: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0
                    }}>
                      <svg width="20" height="20" viewBox="0 0 24 24" fill={hasError ? '#d93025' : '#0061ff'}>
                        <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18.5,9H13V3.5L18.5,9M6,20V4H12V10H18V20H6Z" />
                      </svg>
                    </div>

                    {/* File Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: '15px',
                        fontWeight: '500',
                        color: hasError ? '#d93025' : '#1e1919',
                        marginBottom: '4px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                      }}>
                        {file.name}
                      </div>
                      <div style={{
                        fontSize: '13px',
                        color: '#637381'
                      }}>
                        {formatFileSize(file.size)}
                        {progress !== undefined && ` • ${progress}% uploaded`}
                        {hasError && ` • ${fileValidationErrors[file.name].join(', ')}`}
                      </div>
                    </div>

                    {/* Remove Button */}
                    <button
                      onClick={() => removeFile(index)}
                      disabled={uploading}
                      style={{
                        width: '32px',
                        height: '32px',
                        background: 'transparent',
                        border: 'none',
                        borderRadius: '50%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: uploading ? 'not-allowed' : 'pointer',
                        transition: 'all 0.15s ease',
                        opacity: uploading ? 0.4 : 0.6,
                        flexShrink: 0
                      }}
                      onMouseEnter={(e) => !uploading && (e.currentTarget.style.opacity = '1', e.currentTarget.style.background = '#f0f2f4')}
                      onMouseLeave={(e) => !uploading && (e.currentTarget.style.opacity = '0.6', e.currentTarget.style.background = 'transparent')}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#637381" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                      </svg>
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Processing Options - Horizontal Icon Layout */}
        <div style={{ marginTop: '20px' }}>
          <h3 style={{
            fontSize: '15px',
            fontWeight: '500',
            color: '#1e1919',
            margin: '0 0 12px 0'
          }}>
            Processing options
          </h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '12px'
          }}>
            {/* Extract Text Option */}
            <label
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '10px',
                padding: '16px 12px',
                background: '#ffffff',
                border: options.extractText ? '2px solid #0a0e27' : '1px solid #e1e4e8',
                borderRadius: '8px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                textAlign: 'center'
              }}
              onMouseEnter={(e) => !options.extractText && (e.currentTarget.style.borderColor = '#cbd5e1')}
              onMouseLeave={(e) => !options.extractText && (e.currentTarget.style.borderColor = '#e1e4e8')}
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={options.extractText ? '#0a0e27' : '#64748b'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
              </svg>
              <input
                type="checkbox"
                checked={options.extractText}
                onChange={(e) => handleOptionChange('extractText', e.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  cursor: 'pointer',
                  accentColor: '#0a0e27'
                }}
              />
              <div>
                <div style={{
                  fontSize: '14px',
                  fontWeight: '500',
                  color: '#0a0e27',
                  marginBottom: '4px'
                }}>
                  Extract text
                </div>
                <div style={{
                  fontSize: '12px',
                  color: '#637381',
                  lineHeight: '1.4'
                }}>
                  Get raw text content
                </div>
              </div>
            </label>

            {/* Convert to Markdown Option */}
            <label
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '10px',
                padding: '16px 12px',
                background: '#ffffff',
                border: options.extractMarkdown ? '2px solid #0a0e27' : '1px solid #e1e4e8',
                borderRadius: '8px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                textAlign: 'center'
              }}
              onMouseEnter={(e) => !options.extractMarkdown && (e.currentTarget.style.borderColor = '#cbd5e1')}
              onMouseLeave={(e) => !options.extractMarkdown && (e.currentTarget.style.borderColor = '#e1e4e8')}
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={options.extractMarkdown ? '#0a0e27' : '#64748b'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 7V17C3 18.1046 3.89543 19 5 19H19C20.1046 19 21 18.1046 21 17V7C21 5.89543 20.1046 5 19 5H5C3.89543 5 3 5.89543 3 7Z"></path>
                <polyline points="11 12 7 16 7 8"></polyline>
                <polyline points="17 16 17 8 13 12"></polyline>
              </svg>
              <input
                type="checkbox"
                checked={options.extractMarkdown}
                onChange={(e) => handleOptionChange('extractMarkdown', e.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  cursor: 'pointer',
                  accentColor: '#0a0e27'
                }}
              />
              <div>
                <div style={{
                  fontSize: '14px',
                  fontWeight: '500',
                  color: '#0a0e27',
                  marginBottom: '4px'
                }}>
                  Convert to Markdown
                </div>
                <div style={{
                  fontSize: '12px',
                  color: '#637381',
                  lineHeight: '1.4'
                }}>
                  Format as markdown
                </div>
              </div>
            </label>

            {/* Sync to KB Option */}
            <label
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '10px',
                padding: '16px 12px',
                background: '#ffffff',
                border: options.syncToKB ? '2px solid #0a0e27' : '1px solid #e1e4e8',
                borderRadius: '8px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                textAlign: 'center'
              }}
              onMouseEnter={(e) => !options.syncToKB && (e.currentTarget.style.borderColor = '#cbd5e1')}
              onMouseLeave={(e) => !options.syncToKB && (e.currentTarget.style.borderColor = '#e1e4e8')}
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={options.syncToKB ? '#0a0e27' : '#64748b'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                <polyline points="7.5 4.21 12 6.81 16.5 4.21"></polyline>
                <polyline points="7.5 19.79 7.5 14.6 3 12"></polyline>
                <polyline points="21 12 16.5 14.6 16.5 19.79"></polyline>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                <line x1="12" y1="22.08" x2="12" y2="12"></line>
              </svg>
              <input
                type="checkbox"
                checked={options.syncToKB}
                onChange={(e) => handleOptionChange('syncToKB', e.target.checked)}
                style={{
                  width: '16px',
                  height: '16px',
                  cursor: 'pointer',
                  accentColor: '#0a0e27'
                }}
              />
              <div>
                <div style={{
                  fontSize: '14px',
                  fontWeight: '500',
                  color: '#0a0e27',
                  marginBottom: '4px'
                }}>
                  Sync to KB
                </div>
                <div style={{
                  fontSize: '12px',
                  color: '#637381',
                  lineHeight: '1.4'
                }}>
                  Auto-sync to Bedrock
                </div>
              </div>
            </label>
          </div>
        </div>

        {/* Upload Button - Dropbox Style */}
        {files.length > 0 && (
          <div style={{ marginTop: '20px' }}>
            <button
              onClick={handleUpload}
              disabled={uploading || Object.keys(fileValidationErrors).length > 0}
              style={{
                width: '100%',
                padding: '14px',
                background: uploading || Object.keys(fileValidationErrors).length > 0 ? '#f0f2f4' : '#0a0e27',
                color: uploading || Object.keys(fileValidationErrors).length > 0 ? '#99a4ae' : '#ffffff',
                border: 'none',
                borderRadius: '10px',
                fontSize: '15px',
                fontWeight: '500',
                cursor: uploading || Object.keys(fileValidationErrors).length > 0 ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s ease',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px'
              }}
              onMouseEnter={(e) => {
                if (!uploading && Object.keys(fileValidationErrors).length === 0) {
                  e.currentTarget.style.background = '#05070f'
                }
              }}
              onMouseLeave={(e) => {
                if (!uploading && Object.keys(fileValidationErrors).length === 0) {
                  e.currentTarget.style.background = '#0a0e27'
                }
              }}
            >
              {uploading ? (
                <>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: 'spin 1s linear infinite' }}>
                    <circle cx="12" cy="12" r="10"></circle>
                    <path d="M12 6v6l4 2"></path>
                  </svg>
                  Uploading {files.length} {files.length === 1 ? 'file' : 'files'}...
                </>
              ) : (
                `Upload ${files.length} ${files.length === 1 ? 'file' : 'files'}`
              )}
            </button>
          </div>
        )}

        {uploading && Object.keys(uploadProgress).length > 0 && (
          <Box>
            <Header variant="h3">Upload Progress</Header>
            <SpaceBetween direction="vertical" size="s">
              {Object.entries(uploadProgress).map(([fileName, progress]) => (
                <div key={`progress-${fileName}`}>
                  <Box margin={{ bottom: 'xs' }}>{fileName}</Box>
                  <ProgressBar value={progress} />
                </div>
              ))}
            </SpaceBetween>
          </Box>
        )}

        {uploadResults.length > 0 && (
          <FormField label="Upload Results">
            <Cards
              cardDefinition={{
                header: item => (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box variant="h4">{item.file}</Box>
                    <StatusIndicator type={item.success ? 'success' : 'error'}>
                      {item.success ? 'Success' : 'Failed'}
                    </StatusIndicator>
                  </div>
                ),
                sections: [
                  {
                    content: item => (
                      <Box variant="small">
                        {item.success ? 'Upload completed successfully' : item.error}
                      </Box>
                    )
                  }
                ]
              }}
              items={uploadResults}
              cardsPerRow={[
                { cards: 1 },
                { minWidth: 500, cards: 2 }
              ]}
            />
          </FormField>
        )}

        {/* Recent Uploads - Enhanced */}
        <div style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--spacing-xl)'
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 'var(--spacing-lg)'
          }}>
            <div>
              <h3 style={{
                fontSize: 'var(--font-size-base)',
                fontWeight: 'var(--font-weight-semibold)',
                color: 'var(--color-text-primary)',
                margin: '0 0 4px 0'
              }}>
                Recent Uploads
              </h3>
              <p style={{
                fontSize: 'var(--font-size-sm)',
                color: 'var(--color-text-secondary)',
                margin: 0
              }}>
                Your recently uploaded documents from this session
              </p>
            </div>
            {recentUploads.length > 0 && (
              <button
                onClick={loadRecentUploads}
                disabled={loadingRecentUploads}
                style={{
                  padding: '8px 14px',
                  background: 'var(--color-surface)',
                  color: 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 'var(--font-weight-medium)',
                  cursor: loadingRecentUploads ? 'not-allowed' : 'pointer',
                  transition: 'all var(--transition-base)'
                }}
              >
                {loadingRecentUploads ? '↻ Refreshing...' : '↻ Refresh'}
              </button>
            )}
          </div>

          {loadingRecentUploads ? (
            <div style={{
              padding: '48px',
              textAlign: 'center',
              color: 'var(--color-text-secondary)'
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: 'spin 1s linear infinite', margin: '0 auto 12px' }}>
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M12 6v6l4 2"></path>
              </svg>
              <div style={{ fontSize: 'var(--font-size-sm)' }}>Loading recent uploads...</div>
            </div>
          ) : recentUploads.length > 0 ? (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 'var(--spacing-md)'
            }}>
              {recentUploads.map((item, idx) => (
                <div key={idx} style={{
                  background: 'var(--color-surface-secondary)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: 'var(--spacing-md)',
                  transition: 'all var(--transition-base)'
                }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: '8px'
                  }}>
                    <div style={{
                      fontSize: 'var(--font-size-sm)',
                      fontWeight: 'var(--font-weight-medium)',
                      color: 'var(--color-text-primary)',
                      wordBreak: 'break-word'
                    }}>
                      {item.name}
                    </div>
                    <span style={{
                      padding: '3px 8px',
                      background: item.status === 'completed' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(59, 130, 246, 0.1)',
                      color: item.status === 'completed' ? 'var(--gradient-success)' : 'var(--color-accent)',
                      fontSize: '11px',
                      fontWeight: 'var(--font-weight-semibold)',
                      borderRadius: 'var(--radius-full)',
                      whiteSpace: 'nowrap'
                    }}>
                      {item.status}
                    </span>
                  </div>
                  <div style={{
                    display: 'flex',
                    gap: 'var(--spacing-md)',
                    fontSize: 'var(--font-size-xs)',
                    color: 'var(--color-text-secondary)'
                  }}>
                    <span>{item.uploadTime}</span>
                    <span>•</span>
                    <span>{item.size}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{
              padding: '48px',
              textAlign: 'center'
            }}>
              <div style={{
                width: '64px',
                height: '64px',
                margin: '0 auto 16px',
                background: 'var(--color-surface-secondary)',
                borderRadius: 'var(--radius-lg)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid var(--color-border)'
              }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" strokeWidth="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                </svg>
              </div>
              <div style={{
                fontSize: 'var(--font-size-base)',
                fontWeight: 'var(--font-weight-medium)',
                color: 'var(--color-text-primary)',
                marginBottom: '8px'
              }}>
                No recent uploads
              </div>
              <div style={{
                fontSize: 'var(--font-size-sm)',
                color: 'var(--color-text-secondary)'
              }}>
                Upload your first document to get started with AI-powered analysis
              </div>
            </div>
          )}
        </div>
      </SpaceBetween>
    </div>
  )
}

export default DocumentUpload
