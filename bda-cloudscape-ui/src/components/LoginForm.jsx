import React, { useState } from 'react'
import { signIn, signUp, confirmSignUp } from 'aws-amplify/auth'
import { User, Lock, Mail, Building2, Eye, EyeOff, ArrowRight, Check, AlertCircle } from 'lucide-react'
import styles from './Login.module.css'

function LoginForm({ onSignIn, onError }) {
  const [isSignUp, setIsSignUp] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    confirmPassword: '',
    confirmationCode: '',
    rememberMe: false,
    agreeToTerms: false
  })
  const [errors, setErrors] = useState({})
  const [needsConfirmation, setNeedsConfirmation] = useState(false)
  const [passwordStrength, setPasswordStrength] = useState('')

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }))
    // Clear error for this field when user starts typing
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }))
    }

    // Check password strength for sign-up
    if (name === 'password' && isSignUp) {
      const strength = checkPasswordStrength(value)
      setPasswordStrength(strength)
    }
  }

  const checkPasswordStrength = (password) => {
    if (password.length < 6) return 'weak'

    const hasUpper = /[A-Z]/.test(password)
    const hasLower = /[a-z]/.test(password)
    const hasNumber = /\d/.test(password)
    const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(password)

    const conditions = [hasUpper, hasLower, hasNumber, hasSpecial].filter(Boolean).length

    if (password.length >= 8 && conditions >= 3) return 'strong'
    if (password.length >= 6 && conditions >= 2) return 'medium'
    return 'weak'
  }

  const getPasswordStrengthText = (strength) => {
    switch (strength) {
      case 'weak': return 'Weak password - Add more characters, numbers, and symbols'
      case 'medium': return 'Medium strength - Consider adding more variety'
      case 'strong': return 'Strong password!'
      default: return ''
    }
  }

  const validateForm = () => {
    const newErrors = {}

    if (!formData.email) {
      newErrors.email = 'Email is required'
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email'
    }

    if (isSignUp && !formData.username) {
      newErrors.username = 'Username is required'
    }

    if (!formData.password) {
      newErrors.password = 'Password is required' //  pragma: allowlist secret
    } else if (isSignUp && formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters' //  pragma: allowlist secret
    }

    if (isSignUp && formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match' //  pragma: allowlist secret
    }

    if (isSignUp && !formData.agreeToTerms) {
      newErrors.agreeToTerms = 'You must agree to the terms and conditions'
    }

    return newErrors
  }

  const handleSignIn = async (e) => {
    e.preventDefault()
    const newErrors = validateForm()

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setLoading(true)
    try {
      console.log('Attempting sign in with:', formData.email)
      const signInResult = await signIn({
        username: formData.email,
        password: formData.password
      })
      console.log('SignIn result:', signInResult)
      console.log('SignIn nextStep:', signInResult.nextStep)
      console.log('SignIn isSignedIn:', signInResult.isSignedIn)

      onSignIn(signInResult)
    } catch (err) {
      console.error('Sign in error:', err)
      onError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSignUp = async (e) => {
    e.preventDefault()
    const newErrors = validateForm()

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setLoading(true)
    try {
      await signUp({
        username: formData.username,
        password: formData.password,
        options: {
          userAttributes: {
            email: formData.email
          }
        }
      })
      setNeedsConfirmation(true)
    } catch (err) {
      onError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmSignUp = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await confirmSignUp({
        username: formData.username,
        confirmationCode: formData.confirmationCode
      })
      // After confirmation, sign in automatically
      const user = await signIn({
        username: formData.username,
        password: formData.password
      })
      onSignIn(user)
    } catch (err) {
      onError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    if (isSignUp) {
      await handleSignUp(e)
    } else {
      await handleSignIn(e)
    }
  }

  // Custom Input Component with Icon
  const InputField = ({ icon: IconComponent, name, type, placeholder, value, error, ...props }) => (
    <div className={styles.inputContainer}>
      <div className={`${styles.inputWrapper} ${error ? styles.inputError : ''}`}>
        <IconComponent className={styles.inputIcon} />
        <input
          name={name}
          type={type}
          value={value}
          onChange={handleInputChange}
          placeholder={placeholder}
          className={styles.input}
          {...props}
        />
      </div>
      {error && (
        <div className={styles.errorMessage}>
          <AlertCircle className={styles.errorIcon} />
          <span>{error}</span>
        </div>
      )}
    </div>
  )

  // Custom Password Field Component
  const PasswordField = ({ name, placeholder, value, error }) => (
    <div className={styles.inputContainer}>
      <div className={`${styles.inputWrapper} ${error ? styles.inputError : ''}`}>
        <Lock className={styles.inputIcon} />
        <input
          name={name}
          type={showPassword ? 'text' : 'password'}
          value={value}
          onChange={handleInputChange}
          placeholder={placeholder}
          className={styles.input}
        />
        <button
          type="button"
          onClick={() => setShowPassword(!showPassword)}
          className={styles.passwordToggle}
        >
          {showPassword ? <EyeOff className={styles.passwordIcon} /> : <Eye className={styles.passwordIcon} />}
        </button>
      </div>
      {error && (
        <div className={styles.errorMessage}>
          <AlertCircle className={styles.errorIcon} />
          <span>{error}</span>
        </div>
      )}
    </div>
  )

  if (needsConfirmation) {
    return (
      <div className={styles.loginPage}>
        <div className={styles.loginCard}>
          {/* Logo and Title */}
          <div className={styles.logoSection}>
            <div className={styles.logoIcon}>
              <Mail style={{ width: '40px', height: '40px', color: 'white' }} />
            </div>
            <h1 className={styles.brandTitle}>Check Your Email</h1>
            <p className={styles.brandSubtitle}>We've sent a confirmation code to your email</p>
          </div>

          <div className={styles.formSection}>
            <form onSubmit={handleConfirmSignUp} className={styles.form}>
              <div className={styles.infoAlert}>
                <p>Please check your email for a confirmation code and enter it below.</p>
              </div>

              <InputField
                icon={Lock}
                name="confirmationCode"
                type="text"
                placeholder="Enter 6-digit code"
                value={formData.confirmationCode}
                error={errors.confirmationCode}
                autoComplete="one-time-code"
              />

              <button
                type="submit"
                disabled={loading}
                className={`${styles.submitButton} ${loading ? styles.loadingButton : ''}`}
              >
                {loading ? (
                  <div className={styles.spinner} />
                ) : (
                  <>
                    <span>Confirm Account</span>
                    <ArrowRight className={styles.buttonIcon} />
                  </>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.loginPage}>
      <div className={styles.loginCard}>
        {/* Logo and Title */}
        <div className={styles.logoSection}>
          <div className={styles.logoIcon}>
            <Building2 style={{ width: '40px', height: '40px', color: 'white' }} />
          </div>
          <h1 className={styles.brandTitle}>BDA Investment Platform</h1>
          <p className={styles.brandSubtitle}>Intelligent Document Processing & Analysis</p>
        </div>

        {/* Main Card */}
        <div className={styles.formCard}>
          {/* Tab Switcher */}
          <div className={styles.tabContainer}>
            <button
              onClick={() => setIsSignUp(false)}
              className={`${styles.tab} ${!isSignUp ? styles.activeTab : ''}`}
            >
              Sign In
            </button>
            <button
              onClick={() => setIsSignUp(true)}
              className={`${styles.tab} ${isSignUp ? styles.activeTab : ''}`}
            >
              Sign Up
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className={styles.form}>
            {/* Email Field */}
            <InputField
              icon={Mail}
              name="email"
              type="email"
              placeholder="Email address"
              value={formData.email}
              error={errors.email}
              autoComplete="email"
            />

            {/* Username Field (Sign Up only) */}
            {isSignUp && (
              <InputField
                icon={User}
                name="username"
                type="text"
                placeholder="Username"
                value={formData.username}
                error={errors.username}
                autoComplete="username"
              />
            )}

            {/* Password Field */}
            <PasswordField
              name="password"
              placeholder={isSignUp ? 'Create password' : 'Password'}
              value={formData.password}
              error={errors.password}
            />

            {/* Confirm Password Field (Sign Up only) */}
            {isSignUp && (
              <PasswordField
                name="confirmPassword"
                placeholder="Confirm password"
                value={formData.confirmPassword}
                error={errors.confirmPassword}
              />
            )}

            {/* Remember Me / Terms */}
            <div className={styles.checkboxContainer}>
              {!isSignUp ? (
                <div className={styles.rememberSection}>
                  <label className={styles.checkboxLabel}>
                    <input
                      type="checkbox"
                      name="rememberMe"
                      checked={formData.rememberMe}
                      onChange={handleInputChange}
                      className={styles.hiddenCheckbox}
                    />
                    <div className={`${styles.customCheckbox} ${formData.rememberMe ? styles.checked : ''}`}>
                      {formData.rememberMe && <Check className={styles.checkIcon} />}
                    </div>
                    <span className={styles.checkboxText}>Remember me</span>
                  </label>
                  <a href="#" className={styles.forgotLink}>
                    Forgot password?
                  </a>
                </div>
              ) : (
                <div>
                  <label className={styles.termsLabel}>
                    <input
                      type="checkbox"
                      name="agreeToTerms"
                      checked={formData.agreeToTerms}
                      onChange={handleInputChange}
                      className={styles.hiddenCheckbox}
                    />
                    <div className={`${styles.customCheckbox} ${formData.agreeToTerms ? styles.checked : ''}`}>
                      {formData.agreeToTerms && <Check className={styles.checkIcon} />}
                    </div>
                    <span className={styles.termsText}>
                      I agree to the <a href="#" className={styles.link}>Terms and Conditions</a> and <a href="#" className={styles.link}>Privacy Policy</a>
                    </span>
                  </label>
                  {errors.agreeToTerms && (
                    <div className={styles.errorMessage}>
                      <AlertCircle className={styles.errorIcon} />
                      <span>{errors.agreeToTerms}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className={`${styles.submitButton} ${loading ? styles.loadingButton : ''}`}
            >
              {loading ? (
                <div className={styles.spinner} />
              ) : (
                <>
                  <span>{isSignUp ? 'Create Account' : 'Sign In'}</span>
                  <ArrowRight className={styles.buttonIcon} />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <div className={styles.footerText}>
            {isSignUp ? (
              <span>
                Already have an account?{' '}
                <button
                  onClick={() => setIsSignUp(false)}
                  className={styles.switchButton}
                  type="button"
                >
                  Sign in
                </button>
              </span>
            ) : (
              <span>
                Don't have an account?{' '}
                <button
                  onClick={() => setIsSignUp(true)}
                  className={styles.switchButton}
                  type="button"
                >
                  Sign up for free
                </button>
              </span>
            )}
          </div>
          <div className={styles.securityText}>
            Secured by AWS Cognito • Your data is encrypted and protected
          </div>
        </div>
      </div>
    </div>
  )
}

export default LoginForm