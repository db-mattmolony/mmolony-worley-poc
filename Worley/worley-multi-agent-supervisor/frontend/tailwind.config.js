/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        petrol: {
          50: "#e6eef0",
          100: "#ccdde2",
          200: "#99bbc4",
          300: "#66999f",
          400: "#337781",
          500: "#004d5a",
          600: "#003f4d",
          700: "#003645",
          800: "#002a36",
          900: "#001e27",
        },
        teal: {
          50: "#e9faf9",
          100: "#d3f5f3",
          200: "#a9e9e6",
          300: "#7fdeda",
          400: "#54d3cd",
          500: "#29c8c1",
          600: "#21a09a",
          700: "#197874",
          800: "#10504d",
          900: "#082827",
        },
        coral: {
          500: "#f43a4f",
        },
        lime: {
          400: "#9ada3c",
          500: "#81d114",
        },
        cream: "#faf8ef",
        "ui-gray": "#e6ebed",
      },
      fontFamily: {
        sans: ["Verdana", "Arial", "Helvetica", "sans-serif"],
        heading: ['"Helvetica Neue"', "Helvetica", "Arial", "sans-serif"],
      },
      borderRadius: {
        pill: "2.5rem",
      },
    },
  },
  plugins: [],
};
