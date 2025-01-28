document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("searchButton").addEventListener("click", function () {
        const query = document.getElementById("query").value.trim();
        let teacher = document.getElementById("teacher").value.trim();
        const category = document.getElementById("category").value.trim();
        const date = document.getElementById("date").value.trim();

        // Convert teacher name to lowercase for better filtering
        teacher = teacher.toLowerCase();

        // Build the API URL dynamically
        let apiUrl = `http://127.0.0.1:5000/search?q=${encodeURIComponent(query)}`;
        if (teacher) apiUrl += `&teacher=${encodeURIComponent(teacher)}`;
        if (category) apiUrl += `&category=${encodeURIComponent(category)}`;
        if (date) apiUrl += `&date=${encodeURIComponent(date)}`;

        console.log("🔍 Sending request to:", apiUrl);

        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log("✅ Received data:", data);
                
                // Debugging: Confirm number of results
                console.log(`📌 Total Results Received: ${data.length}`);

                displayResults(data);
            })
            .catch(error => {
                console.error("❌ Error fetching data:", error);
                document.getElementById("results").innerHTML = "<p>Failed to load results. Please try again.</p>";
            });
    });
});

function displayResults(results) {
    const resultsContainer = document.getElementById("results");
    resultsContainer.innerHTML = ""; // Clear previous results

    if (!results.length) {
        resultsContainer.innerHTML = "<p>No results found.</p>";
        return;
    }

    results.forEach(shiur => {
        const shiurElement = document.createElement("div");
        shiurElement.classList.add("shiur");

        shiurElement.innerHTML = `
            <h3>${shiur.title}</h3>
            <p><strong>Teacher:</strong> ${shiur.teacher}</p>
            <p><strong>Series:</strong> ${shiur.series || "N/A"}</p>
            <p><strong>Duration:</strong> ${shiur.duration || "Unknown"}</p>
            <p><strong>Categories:</strong> ${shiur.categories}</p>
            <p><strong>Date:</strong> ${shiur.date}</p>
            <p>
                🎧 <a href="${shiur.download_url}" target="_blank">Download</a> |
                ▶️ <a href="${shiur.player_url}" target="_blank">Listen</a>
            </p>
            ${shiur.image ? `<img src="${shiur.image}" alt="Shiur Image" width="150">` : ""}
        `;

        resultsContainer.appendChild(shiurElement);
    });

    console.log("📌 Final processed results displayed successfully.");
}