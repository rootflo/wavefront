/** @type {import('tailwindcss').Config} */
import tailwindcssAnimate from 'tailwindcss-animate';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx,mdx,html}'],
  extend: {
    colors: {
      heading: '#007EEC',
      admin_bg: '#007EEC0A',
      other_bg: '#00000005',
      thead_bg: '#E8ECF2',
      nav_bg: '#007EEC14',
      border_color: '#E8ECF2',
      gray_text: '#828B92',
      tabs_bg: '#E6EAF1',
      metric_text: '#00000080',
      detailed_tab_div: '#F7FAFF',
      danger: '#DD5252',
      warning: '#DD9752',
      moderate: '#FFBB3D',
      success: '#22A622',
      root_navigation_bg: '#0000000a',
      delete_bg: '#dd525214',
    },
    backgroundImage: {
      'custom-gradient': 'linear-gradient(90deg, #FFBB4D 0%, #E50000 100%)',
    },
    clipPath: {
      triangle: 'polygon(0 0, 0% 100%, 100% 100%)',
    },
    boxShadow: {
      modal: '0px 0px 48px 0px rgba(0, 0, 0, 0.12)',
    },
    fontFamily: {
      'sf-pro': ['"sf-pro-display"'],
    },
    keyframes: {
      fadeIn: {
        '0%': { opacity: '0' },
        '50%': { opacity: '0.5' },
        '100%': { opacity: '1' },
      },
    },
    animation: {
      'fade-in': 'fadeIn 0.75s ease-in-out infinite',
    },
  },
  plugins: [tailwindcssAnimate],
};
