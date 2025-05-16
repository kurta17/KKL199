/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}", // Ensure it covers all your component files
  ],
  theme: {
    extend: {
      // You can extend Tailwind's theme here if needed
      // e.g., custom colors, fonts, animations
    },
  },
  plugins: [],
}