/* static/query.js */

document.addEventListener('DOMContentLoaded', function () {
    const customQueryForm = document.getElementById('customQueryForm');
    const resultsDiv = document.getElementById('results');

    customQueryForm.addEventListener('submit', function (event) {
        event.preventDefault();
        const query = document.getElementById('customQuery').value.trim();
        const source = document.getElementById('source').value;

        if (!query || !source) {
            alert('Please enter a query and select a data source.');
            return;
        }

        const data = { query, source };

        // Show loading indicator
        resultsDiv.innerHTML = '<p class="text-gray-600">Executing query...</p>';

        fetch('/execute_custom_query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data),
        })
        .then(response => response.json())
        .then(results => displayResults(results))
        .catch(error => {
            console.error('Error executing custom query:', error);
            resultsDiv.innerHTML = '<p class="text-red-500">Error executing custom query. Please try again.</p>';
        });
    });

    // Function to display results (same as in other scripts)
    function displayResults(results) {
        if (results.error) {
            resultsDiv.innerHTML = `<p class="text-red-500">Error: ${results.error}</p>`;
            return;
        }
        if (results.length === 0) {
            resultsDiv.innerHTML = '<p class="text-gray-600">No results found.</p>';
            return;
        }

        let tableHtml = '<div class="table-responsive"><table class="table-auto"><thead><tr>';

        // Create table headers
        for (const key in results[0]) {
            tableHtml += `<th>${key}</th>`;
        }
        tableHtml += '</tr></thead><tbody>';

        // Create table rows
        results.forEach((row, index) => {
            tableHtml += `<tr>`;
            for (const key in row) {
                tableHtml += `<td>${row[key]}</td>`;
            }
            tableHtml += '</tr>';
        });

        tableHtml += '</tbody></table></div>';
        resultsDiv.innerHTML = tableHtml;
    }
});
