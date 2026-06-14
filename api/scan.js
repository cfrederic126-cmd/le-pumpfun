export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST");

  const { address, chainId, type } = req.query;
  const ETH_KEY = "3D4JCN1UV1FISDW3M5ZYGZDPTCP5N9Z24B";
  const SOL_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3ODExNTg5MzkxMTYsImVtYWlsIjoiY2ZyZWRlcmljMTI2QGdtYWlsLmNvbSIsImFjdGlvbiI6InRva2VuLWFwaSIsImFwaVZlcnNpb24iOiJ2MiIsImlhdCI6MTc4MTE1ODkzOX0.3b8NA4wltk3CvbTI1djCtv4TSSgIpBWyKJRz02zLs18";
  const NOWPAYMENTS_KEY = "BFXHH29-3FAM0XM-NHEP2VX-NSFCZV4";

  try {
    if (type === "solana") {
      const url = `https://pro-api.solscan.io/v2.0/account/transactions?address=${address}&limit=50`;
      const response = await fetch(url, { headers: { token: SOL_KEY } });
      const data = await response.json();
      res.status(200).json(data);
    } else if (type === "block") {
      const hex = "0x" + parseInt(address).toString(16);
      const url = `https://api.etherscan.io/v2/api?chainid=${chainId}&module=proxy&action=eth_getBlockByNumber&tag=${hex}&boolean=true&apikey=${ETH_KEY}`;
      const response = await fetch(url);
      const data = await response.json();
      res.status(200).json(data);
    } else if (type === "blocknumber") {
      const url = `https://api.etherscan.io/v2/api?chainid=${chainId}&module=proxy&action=eth_blockNumber&apikey=${ETH_KEY}`;
      const response = await fetch(url);
      const data = await response.json();
      res.status(200).json(data);
    } else if (type === "code") {
      const url = `https://api.etherscan.io/v2/api?chainid=${chainId}&module=proxy&action=eth_getCode&address=${address}&tag=latest&apikey=${ETH_KEY}`;
      const response = await fetch(url);
      const data = await response.json();
      res.status(200).json(data);
    } else if (type === "create_payment") {
      let body = "";
      for await (const chunk of req) body += chunk;
      const { amount, order_id } = JSON.parse(body);

      const payRes = await fetch("https://api.nowpayments.io/v1/payment", {
        method: "POST",
        headers: {
          "x-api-key": NOWPAYMENTS_KEY,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          price_amount: amount,
          price_currency: "eur",
          pay_currency: "usdcsol",
          order_id: order_id,
          order_description: "Guide de récupération CryptoRescue",
        }),
      });
      const payData = await payRes.json();
      res.status(200).json(payData);
    } else if (type === "payment_status") {
      const { payment_id } = req.query;
      const statusRes = await fetch(`https://api.nowpayments.io/v1/payment/${payment_id}`, {
        headers: { "x-api-key": NOWPAYMENTS_KEY },
      });
      const statusData = await statusRes.json();
      res.status(200).json(statusData);
    } else {
      const url = `https://api.etherscan.io/v2/api?chainid=${chainId}&module=account&action=txlist&address=${address}&startblock=0&endblock=99999999&sort=desc&offset=50&page=1&apikey=${ETH_KEY}`;
      const response = await fetch(url);
      const data = await response.json();
      res.status(200).json(data);
    }
  } catch (error) {
    res.status(500).json({ error: "Erreur serveur", details: error.message });
  }
}
