/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        './templates/**/*.html',
        './**/templates/**/*.html',
    ],
    theme: {
        extend: {
            colors: {
                'primary-gold': '#D4AF37',
                'primary-brown': '#4A3728',
                'soft-cream': '#FDFBF7',
                'gold': '#D4AF37',
                'brown': '#4A3728',
            },
            fontFamily: {
                sans: ['Outfit', 'sans-serif'],
                serif: ['Outfit', 'serif'],
            }
        },
    },
    plugins: [],
}
