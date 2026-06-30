using System;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Identity.Client;
using DotNetEnv;

namespace CliClient
{
    class Program
    {
        static async Task Main(string[] args)
        {
            // Load credentials from .env.client (located at the repo root)
            string repoRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../../"));
            string envPath = Path.Combine(repoRoot, ".env.client");

            if (!File.Exists(envPath))
            {
                Console.WriteLine($"Error: {envPath} not found.");
                Console.WriteLine("Please run the setup scripts (setup/setup_all.sh) to generate it.");
                return;
            }

            Env.Load(envPath);

            string tenantId = Environment.GetEnvironmentVariable("AZURE_TENANT_ID")!;
            string clientId = Environment.GetEnvironmentVariable("CLIENT_ID")!;
            string clientSecret = Environment.GetEnvironmentVariable("CLIENT_SECRET")!;
            string apiScope = Environment.GetEnvironmentVariable("API_SCOPE")!;

            string authority = $"https://login.microsoftonline.com/{tenantId}";
            string apiBaseUrl = "http://localhost:8000/api";

            Console.WriteLine("=============================================");
            Console.WriteLine("  C# CLI Client (Service-to-Service)");
            Console.WriteLine("=============================================\n");

            // 1. Initialize MSAL Confidential Client
            IConfidentialClientApplication app = ConfidentialClientApplicationBuilder.Create(clientId)
                .WithClientSecret(clientSecret)
                .WithAuthority(new Uri(authority))
                .Build();

            Console.WriteLine("1. Requesting token from Azure AD...");

            AuthenticationResult? result = null;
            try
            {
                // The scope MUST be the Application ID URI of the API followed by /.default
                result = await app.AcquireTokenForClient(new string[] { apiScope }).ExecuteAsync();
                Console.WriteLine("✅ Token acquired successfully!\n");
            }
            catch (MsalServiceException ex)
            {
                Console.WriteLine($"❌ Failed to acquire token: {ex.Message}");
                return;
            }

            // 2. Prepare HttpClient
            using HttpClient httpClient = new HttpClient();
            httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", result.AccessToken);

            // 3. Test the /api/items GET endpoint (Requires Read role)
            Console.WriteLine("2. Fetching items (GET /api/items)...");
            HttpResponseMessage getResponse = await httpClient.GetAsync($"{apiBaseUrl}/items");
            
            string getContent = await getResponse.Content.ReadAsStringAsync();
            if (getResponse.IsSuccessStatusCode)
            {
                Console.WriteLine($"✅ Success: {getContent}\n");
            }
            else
            {
                Console.WriteLine($"❌ Failed ({getResponse.StatusCode}): {getContent}\n");
            }

            // 4. Test the /api/items POST endpoint (Requires Write role)
            Console.WriteLine("3. Creating an item (POST /api/items)...");
            
            var newItem = new { name = "Item from C# CLI", description = "Created automatically via Client Credentials flow" };
            var jsonContent = new StringContent(JsonSerializer.Serialize(newItem), Encoding.UTF8, "application/json");

            HttpResponseMessage postResponse = await httpClient.PostAsync($"{apiBaseUrl}/items", jsonContent);
            
            string postContent = await postResponse.Content.ReadAsStringAsync();
            if (postResponse.IsSuccessStatusCode)
            {
                Console.WriteLine($"✅ Success: {postContent}\n");
            }
            else
            {
                Console.WriteLine($"❌ Failed ({postResponse.StatusCode}): {postContent}\n");
            }

            Console.WriteLine("Done!");
        }
    }
}
