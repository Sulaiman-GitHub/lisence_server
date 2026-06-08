# License Server

This is the central license server for the Cure Pharmaceutical Management System.

## Deployment to Railway

1.  Create a new GitHub repository and push the contents of the `license_server` folder to it.
2.  Login to [Railway.app](https://railway.app/).
3.  Click **"New Project"** -> **"Deploy from GitHub repo"**.
4.  Select your repository.
5.  Add the following **Environment Variables** in Railway:
    *   `ADMIN_SECRET`: A secure string for generating new keys (e.g., `your-very-secure-secret`).
6.  Railway will automatically detect the `Procfile` and deploy the app.

## Endpoints

*   `POST /activate`: Activate a new license key.
*   `POST /validate`: Validate an existing activation.
*   `POST /admin/generate`: Generate a new license key (requires `Admin-Secret` header).
