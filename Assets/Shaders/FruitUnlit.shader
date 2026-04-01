Shader "Foraging/FruitUnlit"
{
    Properties
    {
        _Color("Color", Color) = (1,1,1,1)
    }

    SubShader
    {
        Tags
        {
            "RenderType"="Opaque"
            "Queue"="Geometry"
            "RenderPipeline"="UniversalPipeline"
        }

        Pass
        {
            Name "FruitLit"
            Tags { "LightMode"="UniversalForward" }

            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _SHADOWS_SOFT

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _Color;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
            };

            struct Varyings
            {
                float4 positionHCS : SV_POSITION;
                float3 positionWS  : TEXCOORD0;
                float3 normalWS    : TEXCOORD1;
                float4 shadowCoord : TEXCOORD2;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                float3 positionWS = TransformObjectToWorld(v.positionOS.xyz);
                float3 normalWS = TransformObjectToWorldNormal(v.normalOS);

                o.positionWS = positionWS;
                o.normalWS = normalWS;
                o.positionHCS = TransformWorldToHClip(positionWS);
                o.shadowCoord = TransformWorldToShadowCoord(positionWS);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                // Normalize world-space normal and compute main light with shadows.
                float3 normalWS = normalize(i.normalWS);
                Light mainLight = GetMainLight(i.shadowCoord);

                // View direction from world position toward camera.
                float3 viewDir = normalize(_WorldSpaceCameraPos.xyz - i.positionWS);
                float3 lightDir = normalize(mainLight.direction);

                // Blinn-Phong specular highlight.
                float3 halfDir = normalize(lightDir + viewDir);
                float spec = pow(saturate(dot(normalWS, halfDir)), 64.0);
                float3 specular = mainLight.color.rgb * spec * 0.5;

                // Base fruit color (always full, no diffuse darkening).
                float3 baseColor = _Color.rgb;

                // Combine base and specular.
                float3 litColor = baseColor + specular;

                // Ambient tint with high floor so fruits never get too dark.
                float3 ambientColor = unity_AmbientSky.rgb;
                float3 ambientScaled = ambientColor * 2.0;
                ambientScaled.r = max(ambientScaled.r, 0.85);
                ambientScaled.g = max(ambientScaled.g, 0.85);
                ambientScaled.b = max(ambientScaled.b, 0.85);

                float3 finalColor = litColor * ambientScaled;

                return half4(finalColor, _Color.a);
            }
            ENDHLSL
        }
    }
}

