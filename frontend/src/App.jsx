import React, { useState, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';

const API_BASE = '/api';

function App() {
  const [activeTab, setActiveTab] = useState('convert'); // 'convert', 'compress', 'batch'
  const [files, setFiles] = useState([]);
  const [jobs, setJobs] = useState({});
  const [errors, setErrors] = useState([]);
  const [options, setOptions] = useState({
    quality: 85,
    maxDimension: 1920,
    createZip: true,
    dpi: 150
  });
  const fileInputRef = useRef(null);
  const pollIntervals = useRef({});

  // Format file size
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Get file icon class
  const getFileIconClass = (filename) => {
    const ext = filename.split('.').pop().toLowerCase();
    if (['docx', 'doc'].includes(ext)) return 'docx';
    if (['pdf'].includes(ext)) return 'pdf';
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'].includes(ext)) return 'image';
    return 'other';
  };

  // Get file icon character
  const getFileIconChar = (filename) => {
    const ext = filename.split('.').pop().toLowerCase();
    if (['docx', 'doc'].includes(ext)) return '📄';
    if (['pdf'].includes(ext)) return '📕';
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'].includes(ext)) return '🖼️';
    if (['zip', 'rar', '7z'].includes(ext)) return '📦';
    return '📎';
  };

  // Get result file icon
  const getResultFileIcon = (filename) => {
    const ext = filename.split('.').pop().toLowerCase();
    if (['pdf'].includes(ext)) return { char: '📕', class: 'pdf' };
    if (['zip'].includes(ext)) return { char: '📦', class: 'zip' };
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return { char: '🖼️', class: 'image' };
    return { char: '📎', class: 'pdf' };
  };

  // Handle file selection
  const handleFilesSelected = useCallback((newFiles) => {
    const validFiles = Array.from(newFiles).filter(file => {
      // Check file size (max 100MB)
      if (file.size > 100 * 1024 * 1024) {
        addError(`File "${file.name}" is too large (max 100MB)`);
        return false;
      }
      return true;
    });

    setFiles(prev => [...prev, ...validFiles]);
  }, []);

  // Handle drag and drop
  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add('drag-over');
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-over');
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-over');
    
    if (e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  // Remove file
  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Clear all files
  const clearFiles = () => {
    setFiles([]);
  };

  // Add error
  const addError = (message) => {
    setErrors(prev => [...prev, { id: Date.now(), message }]);
  };

  // Dismiss error
  const dismissError = (id) => {
    setErrors(prev => prev.filter(e => e.id !== id));
  };

  // Start conversion job
  const startConversion = async () => {
    if (files.length === 0) {
      addError('Please select at least one file');
      return;
    }

    // Validate file types for conversion tab
    if (activeTab === 'convert') {
      const invalidFiles = files.filter(f => !f.name.toLowerCase().endsWith('.docx') && !f.name.toLowerCase().endsWith('.doc'));
      if (invalidFiles.length > 0) {
        addError('Only DOCX/DOC files are supported for PDF conversion');
        return;
      }
    }

    for (const file of files) {
      const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      
      // Initialize job status
      setJobs(prev => ({
        ...prev,
        [jobId]: {
          job_id: jobId,
          status: 'pending',
          progress: 0,
          message: 'Starting...',
          result_files: [],
          error: null,
          originalFile: file.name
        }
      }));

      try {
        const formData = new FormData();
        formData.append('file', file);
        
        if (activeTab === 'convert') {
          formData.append('quality', options.quality);
          formData.append('dpi', options.dpi);
          
          const response = await axios.post(`${API_BASE}/convert/docx-to-pdf`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
          });
          
          if (response.data.job_id) {
            startPolling(response.data.job_id, file.name);
          }
        } else if (activeTab === 'compress') {
          formData.append('quality', options.quality);
          formData.append('max_dimension', options.maxDimension);
          
          const response = await axios.post(`${API_BASE}/compress/file`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
          });
          
          if (response.data.job_id) {
            startPolling(response.data.job_id, file.name);
          }
        }
      } catch (error) {
        console.error('Error starting job:', error);
        setJobs(prev => ({
          ...prev,
          [jobId]: {
            ...prev[jobId],
            status: 'failed',
            progress: 0,
            message: 'Failed to start',
            error: error.response?.data?.detail || error.message
          }
        }));
      }
    }

    // Clear files after starting
    clearFiles();
  };

  // Start batch compression
  const startBatchCompression = async () => {
    if (files.length === 0) {
      addError('Please select at least one file');
      return;
    }

    const jobId = `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    setJobs(prev => ({
      ...prev,
      [jobId]: {
        job_id: jobId,
        status: 'pending',
        progress: 0,
        message: 'Starting batch compression...',
        result_files: [],
        error: null,
        originalFile: `${files.length} files`
      }
    }));

    try {
      const formData = new FormData();
      files.forEach(file => formData.append('files', file));
      formData.append('quality', options.quality);
      formData.append('create_zip', options.createZip);
      
      const response = await axios.post(`${API_BASE}/compress/batch`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      
      if (response.data.job_id) {
        startPolling(response.data.job_id, `${files.length} files`);
      }
    } catch (error) {
      console.error('Error starting batch job:', error);
      setJobs(prev => ({
        ...prev,
        [jobId]: {
          ...prev[jobId],
          status: 'failed',
          progress: 0,
          message: 'Failed to start',
          error: error.response?.data?.detail || error.message
        }
      }));
    }

    clearFiles();
  };

  // Poll job status
  const startPolling = (jobId, originalFile) => {
    if (pollIntervals.current[jobId]) {
      clearInterval(pollIntervals.current[jobId]);
    }

    const poll = async () => {
      try {
        const response = await axios.get(`${API_BASE}/status/${jobId}`);
        const job = response.data;
        
        setJobs(prev => ({
          ...prev,
          [jobId]: {
            ...prev[jobId],
            ...job,
            originalFile
          }
        }));

        if (job.status === 'completed' || job.status === 'failed') {
          clearInterval(pollIntervals.current[jobId]);
          delete pollIntervals.current[jobId];
        }
      } catch (error) {
        console.error('Polling error:', error);
        setJobs(prev => ({
          ...prev,
          [jobId]: {
            ...prev[jobId],
            status: 'failed',
            error: 'Failed to check status'
          }
        }));
        clearInterval(pollIntervals.current[jobId]);
        delete pollIntervals.current[jobId];
      }
    };

    pollIntervals.current[jobId] = setInterval(poll, 1000);
    poll(); // Initial poll
  };

  // Download file
  const downloadFile = async (jobId, filename) => {
    try {
      const response = await axios.get(`${API_BASE}/download/${jobId}`, {
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download error:', error);
      addError(`Failed to download ${filename}`);
    }
  };

  // Remove job
  const removeJob = (jobId) => {
    if (pollIntervals.current[jobId]) {
      clearInterval(pollIntervals.current[jobId]);
      delete pollIntervals.current[jobId];
    }
    setJobs(prev => {
      const newJobs = { ...prev };
      delete newJobs[jobId];
      return newJobs;
    });
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      Object.values(pollIntervals.current).forEach(interval => clearInterval(interval));
    };
  }, []);

  // Calculate stats
  const completedJobs = Object.values(jobs).filter(j => j.status === 'completed');
  const totalOriginalSize = completedJobs.reduce((sum, job) => {
    // We don't have original size in job, so we'll estimate
    return sum;
  }, 0);

  const renderTabContent = () => {
    switch (activeTab) {
      case 'convert':
        return (
          <div>
            <div className="drop-zone" 
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input
                type="file"
                className="file-input"
                accept=".docx,.doc"
                multiple
                onChange={(e) => handleFilesSelected(e.target.files)}
                ref={fileInputRef}
              />
              <div className="drop-zone-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="16" y1="13" x2="8" y2="13"></line>
                  <line x1="16" y1="17" x2="8" y2="17"></line>
                  <polyline points="10 9 9 9 8 9"></polyline>
                </svg>
              </div>
              <h3>Convert DOCX to PDF</h3>
              <p>Drag & drop DOCX/DOC files here, or click to browse</p>
              <small>Maximum file size: 100MB per file</small>
            </div>

            {files.length > 0 && (
              <div className="file-list">
                {files.map((file, index) => (
                  <div key={index} className="file-item">
                    <div className={`file-icon ${getFileIconClass(file.name)}`}>
                      {getFileIconChar(file.name)}
                    </div>
                    <div className="file-info">
                      <div className="file-name">{file.name}</div>
                      <div className="file-size">{formatFileSize(file.size)}</div>
                    </div>
                    <button className="file-remove" onClick={() => removeFile(index)}>✕</button>
                  </div>
                ))}
                <button className="btn btn-secondary" onClick={clearFiles} style={{marginTop: '12px', width: '100%'}}>
                  Clear All
                </button>
              </div>
            )}

            <div className="options">
              <h4>Conversion Options</h4>
              <div className="option-group">
                <label>Output Quality: {options.quality}%</label>
                <input
                  type="range"
                  min="50"
                  max="100"
                  value={options.quality}
                  onChange={(e) => setOptions(prev => ({ ...prev, quality: parseInt(e.target.value) }))}
                />
              </div>
              <div className="option-group">
                <label>DPI (Resolution): {options.dpi}</label>
                <input
                  type="range"
                  min="72"
                  max="300"
                  value={options.dpi}
                  onChange={(e) => setOptions(prev => ({ ...prev, dpi: parseInt(e.target.value) }))}
                />
              </div>
            </div>

            <div className="action-buttons">
              <button 
                className="btn btn-primary" 
                onClick={startConversion}
                disabled={files.length === 0}
              >
                🔄 Convert to PDF
              </button>
            </div>
          </div>
        );

      case 'compress':
        return (
          <div>
            <div className="drop-zone" 
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input
                type="file"
                className="file-input"
                multiple
                onChange={(e) => handleFilesSelected(e.target.files)}
                ref={fileInputRef}
              />
              <div className="drop-zone-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="16 18 22 12 16 6"></polyline>
                  <polyline points="8 18 2 12 8 6"></polyline>
                </svg>
              </div>
              <h3>Compress Files</h3>
              <p>Drag & drop images, PDFs, DOCX, or any files here</p>
              <small>Supports: Images (JPG, PNG, WebP), PDF, DOCX, and more • Max 100MB per file</small>
            </div>

            {files.length > 0 && (
              <div className="file-list">
                {files.map((file, index) => (
                  <div key={index} className="file-item">
                    <div className={`file-icon ${getFileIconClass(file.name)}`}>
                      {getFileIconChar(file.name)}
                    </div>
                    <div className="file-info">
                      <div className="file-name">{file.name}</div>
                      <div className="file-size">{formatFileSize(file.size)}</div>
                    </div>
                    <button className="file-remove" onClick={() => removeFile(index)}>✕</button>
                  </div>
                ))}
                <button className="btn btn-secondary" onClick={clearFiles} style={{marginTop: '12px', width: '100%'}}>
                  Clear All
                </button>
              </div>
            )}

            <div className="options">
              <h4>Compression Options</h4>
              <div className="option-group">
                <label>Image Quality: {options.quality}%</label>
                <input
                  type="range"
                  min="10"
                  max="100"
                  value={options.quality}
                  onChange={(e) => setOptions(prev => ({ ...prev, quality: parseInt(e.target.value) }))}
                />
              </div>
              <div className="option-group">
                <label>Max Dimension: {options.maxDimension}px</label>
                <input
                  type="range"
                  min="400"
                  max="3840"
                  step="100"
                  value={options.maxDimension}
                  onChange={(e) => setOptions(prev => ({ ...prev, maxDimension: parseInt(e.target.value) }))}
                />
              </div>
            </div>

            <div className="action-buttons">
              <button 
                className="btn btn-primary" 
                onClick={startConversion}
                disabled={files.length === 0}
              >
                🗜️ Compress Files
              </button>
            </div>
          </div>
        );

      case 'batch':
        return (
          <div>
            <div className="drop-zone" 
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input
                type="file"
                className="file-input"
                multiple
                onChange={(e) => handleFilesSelected(e.target.files)}
                ref={fileInputRef}
              />
              <div className="drop-zone-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                  <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                  <line x1="12" y1="22.08" x2="12" y2="12"></line>
                </svg>
              </div>
              <h3>Batch Compress Multiple Files</h3>
              <p>Drag & drop multiple files to compress them all at once</p>
              <small>Creates a single ZIP archive or individual compressed files • Max 100MB per file</small>
            </div>

            {files.length > 0 && (
              <div className="file-list">
                {files.map((file, index) => (
                  <div key={index} className="file-item">
                    <div className={`file-icon ${getFileIconClass(file.name)}`}>
                      {getFileIconChar(file.name)}
                    </div>
                    <div className="file-info">
                      <div className="file-name">{file.name}</div>
                      <div className="file-size">{formatFileSize(file.size)}</div>
                    </div>
                    <button className="file-remove" onClick={() => removeFile(index)}>✕</button>
                  </div>
                ))}
                <button className="btn btn-secondary" onClick={clearFiles} style={{marginTop: '12px', width: '100%'}}>
                  Clear All
                </button>
              </div>
            )}

            <div className="options">
              <h4>Batch Options</h4>
              <div className="option-group">
                <label>Compression Quality: {options.quality}%</label>
                <input
                  type="range"
                  min="10"
                  max="100"
                  value={options.quality}
                  onChange={(e) => setOptions(prev => ({ ...prev, quality: parseInt(e.target.value) }))}
                />
              </div>
              <div className="option-group">
                <label>
                  <input
                    type="checkbox"
                    checked={options.createZip}
                    onChange={(e) => setOptions(prev => ({ ...prev, createZip: e.target.checked }))}
                  />
                  Create single ZIP archive (uncheck for individual files)
                </label>
              </div>
            </div>

            <div className="action-buttons">
              <button 
                className="btn btn-primary" 
                onClick={startBatchCompression}
                disabled={files.length === 0}
              >
                📦 Batch Compress
              </button>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="app">
      <div className="container">
        <header className="header">
          <h1>📄 DOCX to PDF Converter</h1>
          <p>Convert documents & compress files with ease</p>
        </header>

        <nav className="tabs">
          <button 
            className={`tab ${activeTab === 'convert' ? 'active' : ''}`}
            onClick={() => setActiveTab('convert')}
          >
            🔄 Convert to PDF
          </button>
          <button 
            className={`tab ${activeTab === 'compress' ? 'active' : ''}`}
            onClick={() => setActiveTab('compress')}
          >
            🗜️ Compress Files
          </button>
          <button 
            className={`tab ${activeTab === 'batch' ? 'active' : ''}`}
            onClick={() => setActiveTab('batch')}
          >
            📦 Batch Compress
          </button>
        </nav>

        <div className="content">
          {errors.map(error => (
            <div key={error.id} className="error-message">
              <span>{error.message}</span>
              <button className="error-dismiss" onClick={() => dismissError(error.id)}>✕</button>
            </div>
          ))}

          {renderTabContent()}

          {/* Job Status Section */}
          {Object.keys(jobs).length > 0 && (
            <div className="job-status">
              <h3 style={{marginBottom: '16px', color: '#333'}}>
                Processing Jobs ({Object.keys(jobs).length})
              </h3>
              {Object.entries(jobs).map(([jobId, job]) => (
                <div key={jobId} className="status-card">
                  <div className="status-header">
                    <div>
                      <strong>{job.originalFile}</strong>
                      <span className={`status-badge ${job.status}`} style={{marginLeft: '12px'}}>
                        {job.status}
                      </span>
                    </div>
                    <button className="btn-secondary" onClick={() => removeJob(jobId)} style={{padding: '6px 12px', fontSize: '0.875rem'}}>
                      Remove
                    </button>
                  </div>

                  <div className="progress-bar">
                    <div 
                      className="progress-fill" 
                      style={{width: `${job.progress}%`}}
                    ></div>
                  </div>

                  <div className="status-message">{job.message}</div>

                  {job.error && (
                    <div className="error-message" style={{marginTop: '12px'}}>
                      <span>Error: {job.error}</span>
                    </div>
                  )}

                  {job.status === 'completed' && job.result_files && job.result_files.length > 0 && (
                    <div className="result-files">
                      {job.result_files.map((filename, idx) => {
                        const icon = getResultFileIcon(filename);
                        return (
                          <div key={idx} className="result-file">
                            <div className="result-file-info">
                              <div className={`result-file-icon ${icon.class}`}>
                                {icon.char}
                              </div>
                              <div>
                                <div className="result-file-name">{filename}</div>
                              </div>
                            </div>
                            <button 
                              className="btn-download"
                              onClick={() => downloadFile(jobId, filename)}
                            >
                              ⬇️ Download
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;