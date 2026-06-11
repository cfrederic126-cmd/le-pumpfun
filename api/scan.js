export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET");

  const { address, chainId, type } = req.query;
  const ETH_KEY = "3D4JCN1UV1FISDW3M5ZYGZDPTCP5N9Z24B";
  const SOL_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkQXQiOjE3ODExNTg5MzkxMTYsImVtYWlsIjoiY2ZyZWRlcmljMTI2QGdtYWlsLmNvbSIsImFjdGlvbiI6InRva2VuLWFwaSIsImFwaVZlcnNpb24iOiJ2MiIsImlhdCI6MTc4MTE1ODkzOX0.3b8NA4wltk3CvbTI1djCtv4TSSgIpBWyKJRz02zLs18";

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
    } else {
      const url = `https://api.etherscan.io/v2/api?chainid=${chainId}&module=account&action=txlist&address=${address}&startblock=0&endblock=99999999&sort=desc&offset=50&page=1&apikey=${ETH_KEY}`;
      const response = await fetch(url);
      const data = await response.json();
      res.status(200).json(data);
    }
  } catch (error) {
    res.status(500).json({ error: "Erreur serveur" });
  }
}
