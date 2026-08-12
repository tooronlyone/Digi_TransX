import { forwardRef, useId } from 'react'
import { isValidMpin, nextMpinInput } from '../../auth/accessLock'

const MpinInput = forwardRef(function MpinInput({
  id,
  label = 'Four digit MPIN',
  value,
  onChange,
  disabled = false,
  errorId,
  autoFocus = false,
}, ref) {
  const generatedId = useId()
  const inputId = id || `mpin-${generatedId}`

  function handleChange(event) {
    onChange(nextMpinInput(value, event.target.value))
  }

  function handlePaste(event) {
    const pasted = event.clipboardData.getData('text')
    event.preventDefault()
    if (isValidMpin(pasted)) onChange(pasted)
  }

  return (
    <div className="mpin-control">
      <label className="mpin-control__label" htmlFor={inputId}>{label}</label>
      <div className="mpin-control__input-wrap">
        <input
          ref={ref}
          id={inputId}
          className="mpin-control__input"
          type="password"
          inputMode="numeric"
          pattern="[0-9]{4}"
          maxLength={4}
          autoComplete="off"
          spellCheck="false"
          value={value}
          onChange={handleChange}
          onPaste={handlePaste}
          disabled={disabled}
          aria-describedby={errorId}
          aria-invalid={Boolean(errorId)}
          autoFocus={autoFocus}
        />
        <div className="mpin-control__slots" aria-hidden="true">
          {[0, 1, 2, 3].map((index) => (
            <span className={value.length === index ? 'is-current' : ''} key={index}>
              {value[index] ? '•' : ''}
            </span>
          ))}
        </div>
      </div>
      <p className="mpin-control__hint">Enter exactly four digits.</p>
    </div>
  )
})

export default MpinInput
