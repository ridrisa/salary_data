/* static/salaries.js */

document.addEventListener('DOMContentLoaded', function () {
    const salaryForm = document.getElementById('salaryForm');
    const resultsContainer = document.getElementById('resultsContainer');

    salaryForm.addEventListener('submit', function (event) {
        event.preventDefault();

        const month = document.getElementById('month').value.trim();
        const year = document.getElementById('year').value.trim();

        if (!month || !year) {
            alert('Please select both month and year.');
            return;
        }

        const formData = new FormData(salaryForm);

        // Show loading indicator
        resultsContainer.innerHTML = '<p class="text-gray-600">Calculating salaries...</p>';

        fetch('/salaries', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest' // Important for server-side detection
            },
            body: formData
        })
        .then(response => {
            if (response.ok) {
                return response.text();
            } else {
                // Handle errors
                return response.json().then(err => { throw err; });
            }
        })
        .then(html => {
            // Replace the content of the results container with the new HTML
            resultsContainer.innerHTML = html;

            // Re-initialize the chart if present
            const scriptContent = document.querySelector('#salaryChartScript');
            if (scriptContent) {
                eval(scriptContent.textContent);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            resultsContainer.innerHTML = `<p class="text-red-500">${error.error || 'Error calculating salaries. Please try again.'}</p>`;
        });
    });
});
