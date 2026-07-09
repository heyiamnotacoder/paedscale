interface Props {
  disclaimer: string;
  ntiWarning: string;
}

export default function Disclaimer({ disclaimer, ntiWarning }: Props) {
  return (
    <>
      <div className="disclaimer">{disclaimer}</div>
      {ntiWarning && <div className="disclaimer nti">⚠ {ntiWarning}</div>}
    </>
  );
}
