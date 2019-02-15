pragma solidity ^0.5.3;


/// @title Numerology: A Solidity library for fast ECC arithmetics using curve secp256k1
/// @author David Nuñez (david@nucypher.com)
library Numerology {

    uint256 constant fieldOrder = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F;

    /// @notice Equality test of two points in Jacobian coordinates
    /// @param P An EC point in Jacobian coordinates
    /// @param Q An EC point in Jacobian coordinates
    /// @return true if P and Q represent the same point in affine coordinates; false otherwise
    function eqJacobian(
    	uint256[3] memory P,
    	uint256[3] memory Q
    ) internal pure returns(bool) {
        uint256 p = fieldOrder;

        uint256 Qz = Q[2];
        uint256 Pz = P[2];
        if(Pz == 0){
            return Qz == 0;   // P and Q are both zero.
        } else if(Qz == 0){
            return false;       // Q is zero but P isn't.
        }

        // Now we're sure none of them is zero

        uint256 Q_z_squared = mulmod(Qz, Qz, p);
        uint256 P_z_squared = mulmod(Pz, Pz, p);
        if (mulmod(P[0], Q_z_squared, p) != mulmod(Q[0], P_z_squared, p)){
          return false;
        }

        uint256 Q_z_cubed = mulmod(Q_z_squared, Qz, p);
        uint256 P_z_cubed = mulmod(P_z_squared, Pz, p);
        return mulmod(P[1], Q_z_cubed, p) == mulmod(Q[1], P_z_cubed, p);

    }

    /// @notice Equality test of two points, in affine and Jacobian coordinates respectively
    /// @param P An EC point in affine coordinates
    /// @param Q An EC point in Jacobian coordinates
    /// @return true if P and Q represent the same point in affine coordinates; false otherwise
    function eqAffineJacobian(
    	uint256[2] memory P,
    	uint256[3] memory Q
    ) internal pure returns(bool){
        uint256 Qz = Q[2];
        if(Qz == 0){
            return false;       // Q is zero but P isn't.
        }

        uint256 p = fieldOrder;
        uint256 Q_z_squared = mulmod(Qz, Qz, p);
        return mulmod(P[0], Q_z_squared, p) == Q[0] && mulmod(P[1], mulmod(Q_z_squared, Qz, p), p) == Q[1];

    }


    /// @notice Addition of two points in Jacobian coordinates
    /// @dev Based on the addition formulas from http://www.hyperelliptic.org/EFD/g1p/auto-code/shortw/jacobian-0/addition/add-2001-b.op3
    /// @param P An EC point in Jacobian coordinates
    /// @param Q An EC point in Jacobian coordinates
    /// @return An EC point in Jacobian coordinates with the sum, represented by an array of 3 uint256
    function addJac(
    	uint256[3] memory P,
    	uint256[3] memory Q
    ) internal pure returns (uint256[3] memory R) {

        if(P[2] == 0){
            return Q;
        } else if(Q[2] == 0){
            return P;
        }

        uint256 p = fieldOrder;
        uint256 zz1 = mulmod(P[2], P[2], p);
        uint256 zz2 = mulmod(Q[2], Q[2], p);
        uint256 a   = mulmod(P[0], zz2, p);
        uint256 c   = mulmod(P[1], mulmod(Q[2], zz2, p), p);
        uint256 t0  = mulmod(Q[0], zz1, p);
        uint256 t1  = mulmod(Q[1], mulmod(P[2], zz1, p), p);

        if ((a == t0) && (c == t1)){
            return doubleJacobian(P);
        }
        uint256 d   = addmod(t1, p-c, p); // d = t1 - c
        uint256[3] memory b;
        b[0] = addmod(t0, p-a, p); // b = t0 - a
        b[1] = mulmod(b[0], b[0], p); // e = b^2
        b[2] = mulmod(b[1], b[0], p);  // f = b^3
        uint256 g = mulmod(a, b[1], p);
        R[0] = addmod(mulmod(d, d, p), p-addmod(mulmod(2, g, p), b[2], p), p);
        R[1] = addmod(mulmod(d, addmod(g, p-R[0], p), p), p-mulmod(c, b[2], p), p);
        R[2] = mulmod(b[0], mulmod(P[2], Q[2], p), p);
    }

    /// @notice Addition of two points in Jacobian coordinates, placing the result in the first point
    /// @dev Based on the addition formulas from http://www.hyperelliptic.org/EFD/g1p/auto-code/shortw/jacobian-0/addition/add-2001-b.op3
    /// @param P An EC point in Jacobian coordinates. The result is returned here.
    /// @param Q An EC point in Jacobian coordinates
    function addJacobianMutates(
    	uint[3] memory P,
    	uint[3] memory Q
    ) pure internal {

        uint256 Pz = P[2];
        uint256 Qz = Q[2];

        if(Pz == 0){
            P[0] = Q[0];
            P[1] = Q[1];
            P[2] = Qz;
            return;
        } else if(Qz == 0){
            return;
        }

        uint256 p = fieldOrder;

        uint256 zz = mulmod(Pz, Pz, p);
        uint256 t0  = mulmod(Q[0], zz, p);
        uint256 t1  = mulmod(Q[1], mulmod(Pz, zz, p), p);

        zz = mulmod(Qz, Qz, p);
        uint256 a   = mulmod(P[0], zz, p);
        uint256 c   = mulmod(P[1], mulmod(Qz, zz, p), p);


        if ((a == t0) && (c == t1)){
            doubleMutates(P);
            return;
        }

        t1   = addmod(t1, p-c, p); // d = t1 - c
        uint256 b = addmod(t0, p-a, p); // b = t0 - a
        uint256 e = mulmod(b, b, p); // e = b^2
        t0 = mulmod(a, e, p);    // t0 is actually "g"
        e = mulmod(e, b, p);  // f = b^3  (we will re-use the variable e )
        uint256 temp = addmod(mulmod(t1, t1, p), p-addmod(mulmod(2, t0, p), e, p), p);
        P[0] = temp;
        temp = mulmod(t1, addmod(t0, p-temp, p), p);
        P[1] = addmod(temp, p-mulmod(c, e, p), p);
        P[2] = mulmod(b, mulmod(Pz, Qz, p), p);
    }

    /// @notice Subtraction of two points in Jacobian coordinates, placing the result in the first point
    /// @dev Based on the addition formulas from http://www.hyperelliptic.org/EFD/g1p/auto-code/shortw/jacobian-0/addition/add-2001-b.op3
    /// @param P An EC point in Jacobian coordinates. The result is returned here.
    /// @param Q An EC point in Jacobian coordinates
    function subJacobianMutates(
    	uint[3] memory P,
    	uint[3] memory Q
    ) pure internal {
        uint256 Pz = P[2];
        uint256 Qz = Q[2];
        uint256 p = fieldOrder;

        if(Pz == 0){
            P[0] = Q[0];
            P[1] = p - Q[1];
            P[2] = Qz;
            return;
        } else if(Qz == 0){
            return;
        }

        uint256 zz = mulmod(Pz, Pz, p);
        uint256 t0  = mulmod(Q[0], zz, p);
        uint256 t1  = mulmod(p - Q[1], mulmod(Pz, zz, p), p);

        zz = mulmod(Qz, Qz, p);
        uint256 a   = mulmod(P[0], zz, p);
        uint256 c   = mulmod(P[1], mulmod(Qz, zz, p), p);

        if ((a == t0) && (c == t1)){
            P[2] = 0;
            return;
        }

        t1   = addmod(t1, p-c, p); // d = t1 - c
        uint256 b = addmod(t0, p-a, p); // b = t0 - a
        uint256 e = mulmod(b, b, p); // e = b^2
        t0 = mulmod(a, e, p);    // t0 is actually "g"
        e = mulmod(e, b, p);  // f = b^3  (we will re-use the variable e )
        uint256 temp = addmod(mulmod(t1, t1, p), p-addmod(mulmod(2, t0, p), e, p), p);
        P[0] = temp;
        temp = mulmod(t1, addmod(t0, p-temp, p), p);
        P[1] = addmod(temp, p-mulmod(c, e, p), p);
        P[2] = mulmod(b, mulmod(Pz, Qz, p), p);
    }

    /// @notice Adds two points in affine coordinates, with the result in Jacobian
    /// @dev Based on the addition formulas from http://www.hyperelliptic.org/EFD/g1p/auto-code/shortw/jacobian-0/addition/add-2001-b.op3
    /// @param P An EC point in affine coordinates
    /// @param Q An EC point in affine coordinates
    /// @return An EC point in Jacobian coordinates with the sum, represented by an array of 3 uint256
    function addAffineJacobian(
    	uint[2] memory P,
    	uint[2] memory Q
    ) internal pure returns (uint[3] memory R) {

        uint256 p = fieldOrder;
        uint256 a   = P[0];
        uint256 c   = P[1];
        uint256 t0  = Q[0];
        uint256 t1  = Q[1];

        if ((a == t0) && (c == t1)){
            return doubleJacobian([a, c, 1]);
        }
        uint256 d = addmod(t1, p-c, p); // d = t1 - c
        uint256 b = addmod(t0, p-a, p); // b = t0 - a
        uint256 e = mulmod(b, b, p); // e = b^2
        uint256 f = mulmod(e, b, p);  // f = b^3
        uint256 g = mulmod(a, e, p);
        R[0] = addmod(mulmod(d, d, p), p-addmod(mulmod(2, g, p), f, p), p);
        R[1] = addmod(mulmod(d, addmod(g, p-R[0], p), p), p-mulmod(c, f, p), p);
        R[2] = b;
    }

    /// @notice Point doubling in Jacobian coordinates
    /// @param P An EC point in Jacobian coordinates.
    /// @return An EC point in Jacobian coordinates
    function doubleJacobian(uint[3] memory P) internal pure returns (uint[3] memory Q) {
        uint256 z = P[2];
        if (z == 0)
            return Q;
        uint256 p = fieldOrder;
        uint256 x = P[0];
        uint256 _2y = mulmod(2, P[1], p);
        uint256 _4yy = mulmod(_2y, _2y, p);
        uint256 s = mulmod(_4yy, x, p);
        uint256 m = mulmod(3, mulmod(x, x, p), p);
        uint256 t = addmod(mulmod(m, m, p), mulmod(0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2d, s, p),p);
        Q[0] = t;
        Q[1] = addmod(mulmod(m, addmod(s, p - t, p), p), mulmod(0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffff7ffffe17, mulmod(_4yy, _4yy, p), p), p);
        Q[2] = mulmod(_2y, z, p);
    }

    /// @notice Point doubling in Jacobian coordinates, placing the result in the first point
    /// @param P An EC point in Jacobian coordinates. The result is also stored here.
    function doubleMutates(uint[3] memory P) internal pure {
        uint256 z = P[2];
        if (z == 0)
            return;
        uint256 p = fieldOrder;
        uint256 x = P[0];
        uint256 _2y = mulmod(2, P[1], p);
        uint256 _4yy = mulmod(_2y, _2y, p);
        uint256 s = mulmod(_4yy, x, p);
        uint256 m = mulmod(3, mulmod(x, x, p), p);
        uint256 t = addmod(mulmod(m, m, p), mulmod(0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2d, s, p),p);
        P[0] = t;
        P[1] = addmod(mulmod(m, addmod(s, p - t, p), p), mulmod(0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffff7ffffe17, mulmod(_4yy, _4yy, p), p), p);
        P[2] = mulmod(_2y, z, p);
    }

    function _lookup_sim_mul(
    	uint256[3][4][4] memory iP,
    	uint256[4] memory P_Q
    ) internal pure {
        uint256 p = fieldOrder;
        uint256 beta = 0x7ae96a2b657c07106e64479eac3434e99cf0497512f58995c1396c28719501ee;

        uint256[3][4] memory iPj;
        uint256[3] memory double;

        // P1 Lookup Table
        iPj = iP[0];
        iPj[0] = [P_Q[0], P_Q[1], 1];  						// P1

        double = doubleJacobian(iPj[0]);
        iPj[1] = addJac(double, iPj[0]);
        iPj[2] = addJac(double, iPj[1]);
        iPj[3] = addJac(double, iPj[2]);

        // P2 Lookup Table
        iP[1][0] = [mulmod(beta, P_Q[0], p), P_Q[1], 1];	// P2

        iP[1][1] = [mulmod(beta, iPj[1][0], p), iPj[1][1], iPj[1][2]];
        iP[1][2] = [mulmod(beta, iPj[2][0], p), iPj[2][1], iPj[2][2]];
        iP[1][3] = [mulmod(beta, iPj[3][0], p), iPj[3][1], iPj[3][2]];

        // Q1 Lookup Table
        iPj = iP[2];
        iPj[0] = [P_Q[2], P_Q[3], 1];                   	// Q1

        double = doubleJacobian(iPj[0]);
        iPj[1] = addJac(double, iPj[0]);
        iPj[2] = addJac(double, iPj[1]);
        iPj[3] = addJac(double, iPj[2]);

        // Q2 Lookup Table
        iP[3][0] = [mulmod(beta, P_Q[2], p), P_Q[3], 1];	// P2

        iP[3][1] = [mulmod(beta, iPj[1][0], p), iPj[1][1], iPj[1][2]];
        iP[3][2] = [mulmod(beta, iPj[2][0], p), iPj[2][1], iPj[2][2]];
        iP[3][3] = [mulmod(beta, iPj[3][0], p), iPj[3][1], iPj[3][2]];
    }

    /// @notice Computes the WNAF representation of an integer, and puts the resulting array of coefficients in memory
    /// @param d A 256-bit integer
    /// @return (ptr, length) The pointer to the first coefficient, and the total length of the array
    function _wnaf(int256 d) internal pure returns (uint256 ptr, uint256 length){

        int sign = d < 0 ? -1 : int(1);
        uint256 k = uint256(sign * d);

        length = 0;
        assembly
        {
            let ki := 0
            ptr := mload(0x40) // Get free memory pointer
            mstore(0x40, add(ptr, 300)) // Updates free memory pointer to +300 bytes offset
            for { } gt(k, 0) { } { // while k > 0
                if and(k, 1) {  // if k is odd:
                    ki := mod(k, 16)
                    k := add(sub(k, ki), mul(gt(ki, 8), 16))
                    // if sign = 1, store ki; if sign = -1, store 16 - ki
                    mstore8(add(ptr, length), add(mul(ki, sign), sub(8, mul(sign, 8))))
                }
                length := add(length, 1)
                k := div(k, 2)
            }
            //log3(ptr, 1, 0xfabadaacabada, d, length)
        }

        return (ptr, length);
    }

    /// @notice Simultaneous multiplication of the form kP + lQ.
    /// @dev Scalars k and l are expected to be decomposed such that k = k1 + k2 λ, and l = l1 + l2 λ,
    /// where λ is specific to the endomorphism of the curve
    /// @param k_l An array with the decomposition of k and l values, i.e., [k1, k2, l1, l2]
    /// @param P_Q An array with the affine coordinates of both P and Q, i.e., [P1, P2, Q1, Q2]
    function _sim_mul(
    	int256[4] memory k_l,
    	uint256[4] memory P_Q
    ) internal pure returns (uint[3] memory Q) {

    	require(
    		is_on_curve(P_Q[0], P_Q[1]) && is_on_curve(P_Q[2], P_Q[3]),
    		"Invalid points"
    	);

        uint256[4] memory wnaf;
        uint256 max_count = 0;
        uint256 count = 0;

        for(uint j=0; j<4; j++){
            (wnaf[j], count) = _wnaf(k_l[j]);
            if(count > max_count){
                max_count = count;
            }
        }

        Q = _sim_mul_wnaf(wnaf, max_count, P_Q);
    }


    function _sim_mul_wnaf(
    	uint256[4] memory wnaf_ptr,
    	uint256 length,
    	uint256[4] memory P_Q
    ) internal pure returns (uint[3] memory Q) {
        uint256[3][4][4] memory iP;
        _lookup_sim_mul(iP, P_Q);

        // LOOP
        uint256 i = length;
        uint256 ki;
        uint256 ptr;
        while(i > 0) {
            i--;

            doubleMutates(Q);

            ptr = wnaf_ptr[0] + i;
            assembly {
                ki := byte(0, mload(ptr))
            }

            if (ki > 8) {
                subJacobianMutates(Q, iP[0][(15 - ki) / 2]);
            } else if (ki > 0) {
                addJacobianMutates(Q, iP[0][(ki - 1) / 2]);
            }

            ptr = wnaf_ptr[1] + i;
            assembly {
                ki := byte(0, mload(ptr))
            }

            if (ki > 8) {
                subJacobianMutates(Q, iP[1][(15 - ki) / 2]);
            } else if (ki > 0) {
                addJacobianMutates(Q, iP[1][(ki - 1) / 2]);
            }

            ptr = wnaf_ptr[2] + i;
            assembly {
                ki := byte(0, mload(ptr))
            }

            if (ki > 8) {
                subJacobianMutates(Q, iP[2][(15 - ki) / 2]);
            } else if (ki > 0) {
                addJacobianMutates(Q, iP[2][(ki - 1) / 2]);
            }

            ptr = wnaf_ptr[3] + i;
            assembly {
                ki := byte(0, mload(ptr))
            }

            if (ki > 8) {
                subJacobianMutates(Q, iP[3][(15 - ki) / 2]);
            } else if (ki > 0) {
                addJacobianMutates(Q, iP[3][(ki - 1) / 2]);
            }

        }
    }

    /// @notice Tests if a point is on the secp256k1 curve
    /// @param Px The X coordinate of an EC point in affine representation
    /// @param Py The Y coordinate of an EC point in affine representation
    /// @return true if (Px, Py) is a valid secp256k1 point; false otherwise
    function is_on_curve(uint256 Px, uint256 Py) internal pure returns (bool) {
        uint256 p = fieldOrder;

        if (Px >= p || Py >= p){
            return false;
        }

        uint256 y2 = mulmod(Py, Py, p);
        uint256 x3_plus_7 = addmod(mulmod(mulmod(Px, Px, p), Px, p), 7, p);
        return y2 == x3_plus_7;
    }

    // https://ethresear.ch/t/you-can-kinda-abuse-ecrecover-to-do-ecmul-in-secp256k1-today/2384/4
    function ecmulVerify(
    	uint256 x1,
    	uint256 y1,
    	uint256 scalar,
    	uint256 qx,
    	uint256 qy
    ) internal pure returns(bool) {
	    uint256 curve_order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
	    address signer = ecrecover(0, uint8(27 + (y1 % 2)), bytes32(x1), bytes32(mulmod(scalar, x1, curve_order)));
	    address xyAddress = address(uint256(keccak256(abi.encodePacked(qx, qy))) & 0x00FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF);
	    return xyAddress == signer;
	}

	/// @notice Tests if a compressed point is valid, wrt to its corresponding Y coordinate
    /// @param _pointSign The sign byte from the compressed notation: 0x02 if the Y coord is even; 0x03 otherwise
    /// @param _pointX The X coordinate of an EC point in affine representation
    /// @param _pointY The Y coordinate of an EC point in affine representation
    /// @return true iff _pointSign and _pointX are the compressed representation of (_pointX, _pointY)
	function check_compressed_point(
		uint8 _pointSign,
		uint256 _pointX,
		uint256 _pointY
	) internal pure returns(bool) {
		bool correct_sign = _pointY % 2 == _pointSign - 2;
		return correct_sign && is_on_curve(_pointX, _pointY);
	}

}