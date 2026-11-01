/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  corePlugins: {
    // Disable Tailwind's global reset so the existing hand-written
    // design system (transporter/global.css) is untouched.
    preflight: false,
  },
  plugins: [],
}