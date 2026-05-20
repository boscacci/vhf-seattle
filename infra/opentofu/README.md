# Talking Boats OpenTofu Stack

This stack creates the public static-site edge and the private raw-audio bucket.

It intentionally does **not** create long-lived AWS access keys for the Raspberry
Pi. The Pi should ask the private API for presigned S3 upload URLs.

## Resources

- Private S3 bucket for public static-site files
- CloudFront distribution with Origin Access Control
- ACM certificate in `us-east-1`
- Route 53 `A` and `AAAA` aliases for `talkingboats.robertboscacci.com`
- Private raw-audio S3 bucket with `raw/` lifecycle expiry
- IAM policy for the private server to presign audio, publish reviewed static
  files, and invalidate CloudFront

## Commands

```bash
tofu init
tofu fmt -recursive
tofu validate
tofu plan
```

Run `tofu apply` only after checking bucket names and AWS profile/account.
