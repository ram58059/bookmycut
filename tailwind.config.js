/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        './templates/**/*.html',
        './**/templates/**/*.html',
    ],
    theme: {
        extend: {
            colors: {
                'primary-gold': '#EAB308',
                'primary-brown': '#1F2937',
                'soft-cream': '#FFFFFF',
                'gold': '#EAB308',
                'brown': '#1F2937',
            },
            fontFamily: {
                sans: ['Outfit', 'sans-serif'],
                serif: ['Outfit', 'serif'],
            }
        },
    },
    plugins: [],
}
