export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  const { chainId } = req.query;
  const API_KEY = "3D4JCN1UV1FISDW3M5ZYGZDPTCP5N9Z24B";
  try {
    const url = `https://api.etherscan.io/v2/api?chainid=${chainId}&module=proxy&action=eth_blockNumber&apikey=${API_KEY}`;
    const response = await fetch(url);
    const data = await response.json();
    res.status(200).json(data);
  } catch (error) {
    res.status(500).json({ error: "Erreur serveur" });
  }
}
