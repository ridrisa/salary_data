/* static/config.js */

document.addEventListener('DOMContentLoaded', function () {
    const configForm = document.getElementById('config-form');
    const submitButton = configForm.querySelector('button[type="submit"]');

    configForm.addEventListener('submit', function (event) {
        event.preventDefault();

        const data = {
            project: document.getElementById('project').value.trim(),
            sponsorship_type: document.getElementById('sponsorship_type').value.trim(),
            joining_date: document.getElementById('joining_date').value.trim(),
            basic_salary: document.getElementById('basic_salary').value.trim()
        };

        // Validate form data
        if (!data.project || !data.sponsorship_type || !data.joining_date || !data.basic_salary) {
            alert('Please fill in all fields.');
            return;
        }

        // Disable submit button
        submitButton.disabled = true;
        submitButton.textContent = 'Saving...';

        fetch('/save_salary_configuration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(responseData => {
            alert(responseData.message || responseData.error);
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error saving configuration. Please try again.');
        })
        .finally(() => {
            submitButton.disabled = false;
            submitButton.textContent = 'Save Configuration';
        });
    });
});
